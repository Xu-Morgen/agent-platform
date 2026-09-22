"""不可变修订和文档版本；原件复用流式文件保存，逻辑移除不清理历史。"""
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
from pathlib import Path
import os
import zipfile
import xml.etree.ElementTree as ET
from ..contracts.knowledge import (
    KnowledgeBase, KnowledgeWrite, KnowledgeUpdate, KnowledgeReference, FixedKnowledgeReference,
    KnowledgeRevision, KnowledgePageRequest, KnowledgePage, DocumentVersion, DocumentReadRequest,
)
from ..contracts.errors import ErrorResponse, PlatformError
from ..storage.files import TaskFiles


def knowledge_error(code, message, status=422):
    return PlatformError(ErrorResponse(code=code, stage='knowledge', message=message), status)


def now():
    return datetime.now(timezone.utc).isoformat()


class OriginalFiles(TaskFiles):
    def cleanup(self):
        # 首版仅逻辑移除；已保存版本与失败操作留下的待清理原件均不自动回收。
        pass


class KnowledgeRepository:
    def __init__(self, store, root=None):
        self.store, self.lock = store, RLock()
        self.bases = store.read('knowledge_bases')
        self.revisions = store.read('knowledge_revisions')
        self.versions = store.read('knowledge_versions')
        if root is None and store.durable:
            from ..storage.local import default_data_directory
            root = Path(os.environ.get('AGENT_PLATFORM_DATA_DIR', default_data_directory())) / 'knowledge-originals'
        self.originals = OriginalFiles(store, root, pending_ttl=float('inf'), collection='knowledge_files')

    def close(self):
        self.originals.close()

    def _persist(self, base=None, revision=None, version=None):
        changes = []
        for collection, key_field, model in [('knowledge_bases', 'knowledge_id', base),
                                            ('knowledge_revisions', 'revision_id', revision)]:
            if model is not None:
                changes.append((collection, getattr(model, key_field), model.model_dump(mode='json')))
        if version:
            changes.append(('knowledge_versions', version['metadata']['version_id'], version))
        self.store.write(changes)
        for collection, key, value in changes:
            {'knowledge_bases': self.bases, 'knowledge_revisions': self.revisions,
             'knowledge_versions': self.versions}[collection][key] = value

    def list(self):
        with self.lock:
            return [KnowledgeBase.model_validate(v) for v in self.bases.values()]

    def get(self, knowledge_id, *, active=False):
        with self.lock:
            value = self.bases.get(knowledge_id)
            if value is None:
                raise knowledge_error('KNOWLEDGE_NOT_FOUND', '知识库不存在', 404)
            base = KnowledgeBase.model_validate(value)
            if active and base.archived:
                raise knowledge_error('KNOWLEDGE_ARCHIVED', '知识库已归档，不接受新任务或修改')
            return base

    def create(self, value):
        value = KnowledgeWrite.model_validate(value)
        with self.lock:
            base = KnowledgeBase(knowledge_id='kb_' + uuid4().hex, name=value.name,
                                 revision_id='kr_' + uuid4().hex, created_at=now())
            revision = KnowledgeRevision(knowledge_id=base.knowledge_id, revision_id=base.revision_id,
                                         versions=[], created_at=now())
            self._persist(base, revision)
            return base

    def update(self, knowledge_id, value):
        value = KnowledgeUpdate.model_validate(value)
        with self.lock:
            base = self.get(knowledge_id)
            base.name, base.archived = value.name, value.archived
            self._persist(base=base)
            return base

    def resolve(self, reference, *, active=False):
        reference = KnowledgeReference.model_validate(reference)
        with self.lock:
            base = self.get(reference.knowledge_id, active=active)
            fixed = FixedKnowledgeReference(knowledge_id=base.knowledge_id,
                                           revision_id=reference.revision_id or base.revision_id)
            self.revision(fixed)
            return fixed

    def revision(self, reference):
        reference = FixedKnowledgeReference.model_validate(reference)
        with self.lock:
            raw = self.revisions.get(reference.revision_id)
            if raw is None or raw['knowledge_id'] != reference.knowledge_id:
                raise knowledge_error('KNOWLEDGE_NOT_FOUND', '知识库修订不存在', 404)
            return KnowledgeRevision.model_validate(raw)

    def page(self, request):
        request = KnowledgePageRequest.model_validate(request)
        with self.lock:
            revision = self.revision(request.reference)
            end = request.offset + request.limit
            items = [DocumentVersion.model_validate(self.versions[v]['metadata'])
                     for v in revision.versions[request.offset:end]]
            return KnowledgePage(reference=request.reference, items=items, total=len(revision.versions),
                                 next_offset=end if end < len(revision.versions) else None)

    def metadata(self, request):
        request = DocumentReadRequest.model_validate(request)
        with self.lock:
            if request.version_id not in self.revision(request.reference).versions:
                raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '文档版本不属于指定知识库修订')
            metadata = DocumentVersion.model_validate(self.versions[request.version_id]['metadata'])
            if metadata.size > request.max_bytes:
                raise knowledge_error('KNOWLEDGE_LIMIT_EXCEEDED', '文档超过本次读取大小上限')
            return metadata

    def original(self, request):
        metadata = self.metadata(request)
        try:
            return self.originals.resolve(self.versions[metadata.version_id]['file'])
        except PlatformError as exc:
            if exc.error.code in ('FILE_REFERENCE_INVALID', 'FILE_NOT_FOUND'):
                raise knowledge_error('DOCUMENT_CORRUPTED', '保存的原件损坏或不可读取') from None
            raise

    def history(self, knowledge_id, document_id):
        with self.lock:
            self.get(knowledge_id)
            values = [DocumentVersion.model_validate(v['metadata']) for v in self.versions.values()
                      if v['knowledge_id'] == knowledge_id and v['metadata']['document_id'] == document_id]
            if not values:
                raise knowledge_error('KNOWLEDGE_NOT_FOUND', '文档不存在', 404)
            return values

    def _new_revision(self, base, members, version=None):
        base.revision_id = 'kr_' + uuid4().hex
        revision = KnowledgeRevision(knowledge_id=base.knowledge_id, revision_id=base.revision_id,
                                     versions=members, created_at=now())
        self._persist(base, revision, version)
        return revision

    async def import_document(self, knowledge_id, name, chunks, document_id=None):
        self.get(knowledge_id, active=True)
        if Path(name).suffix.lower() not in ('.docx', '.pdf'):
            raise knowledge_error('FILE_FORMAT_UNSUPPORTED', '知识库仅接受 PDF/DOCX')
        file = await self.originals.save(name, chunks)
        try:
            # PDF 在文件存储层检查扩展名与签名，完整结构和密码由读取块校验。
            # DOCX 保留已有正文 XML 结构检查；平台不提取业务正文。
            path = self.originals.resolve(file)
            if file.format == 'docx':
                try:
                    with zipfile.ZipFile(path) as archive:
                        info = archive.getinfo('word/document.xml')
                        if info.file_size > 50 * 1024 * 1024:
                            raise knowledge_error('KNOWLEDGE_LIMIT_EXCEEDED', 'DOCX 正文 XML 超过 50 MiB')
                        xml = archive.read(info)
                        if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                            raise ValueError('不支持实体声明')
                        root = ET.fromstring(xml)
                        if root.tag != '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document':
                            raise ValueError('DOCX 正文根元素无效')
                except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, RuntimeError, OSError):
                    raise knowledge_error('DOCUMENT_CORRUPTED', 'DOCX 原件结构损坏或不受支持') from None
            with self.lock:
                base = self.get(knowledge_id, active=True)
                members = self.revision(FixedKnowledgeReference(knowledge_id=knowledge_id, revision_id=base.revision_id)).versions
                if document_id:
                    previous = [v for v in members if self.versions[v]['metadata']['document_id'] == document_id]
                    if not previous:
                        raise knowledge_error('KNOWLEDGE_NOT_FOUND', '待替换文档不在当前知识库中', 404)
                else:
                    previous = []
                    document_id = 'doc_' + uuid4().hex
                metadata = DocumentVersion(document_id=document_id, version_id='dv_' + uuid4().hex,
                    original_name=name, format=file.format, size=file.size, sha256=file.sha256, created_at=now())
                members = [metadata.version_id if v in previous else v for v in members]
                if not previous:
                    members.append(metadata.version_id)
                self._new_revision(base, members, {'knowledge_id': knowledge_id,
                    'metadata': metadata.model_dump(mode='json'), 'file': file.model_dump(mode='json')})
                return metadata
        except BaseException:
            self.originals.remove(file.file_id)
            raise

    def remove(self, knowledge_id, document_id):
        with self.lock:
            base = self.get(knowledge_id, active=True)
            old = self.revision(FixedKnowledgeReference(knowledge_id=knowledge_id, revision_id=base.revision_id)).versions
            members = [v for v in old if self.versions[v]['metadata']['document_id'] != document_id]
            if members == old:
                raise knowledge_error('KNOWLEDGE_NOT_FOUND', '文档不在当前知识库中', 404)
            return self._new_revision(base, members)
