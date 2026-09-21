"""任务文件流式保存及摘要验证；元数据随平台文档仓储持久化。"""
import errno
import os
import tempfile
import time
import zipfile
from hashlib import sha256
from pathlib import Path
from threading import RLock
from uuid import uuid4
from ..contracts.files import FileReference
from ..contracts.errors import ErrorResponse, PlatformError


def file_error(code, message):
    return PlatformError(ErrorResponse(code=code, stage='files', message=message), 422)


class TaskFiles:
    def __init__(self, store, root=None, *, max_bytes=50 * 1024 * 1024, pending_ttl=86400, collection='task_files'):
        self.store = store
        self.collection = collection
        self._temporary = None
        if root is None:
            if store.durable:
                from .local import default_data_directory
                root = Path(os.environ.get('AGENT_PLATFORM_DATA_DIR', default_data_directory())) / 'task-files'
            else:
                self._temporary = tempfile.TemporaryDirectory(prefix='agent-files-')
                root = self._temporary.name
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes, self.pending_ttl = max_bytes, pending_ttl
        self.lock = RLock()
        self.items = store.read(self.collection)
        self.cleanup()

    def close(self):
        if self._temporary:
            self._temporary.cleanup()

    def _path(self, file_id):
        import re
        if not re.fullmatch(r'file_[a-f0-9]{32}', file_id):
            raise file_error('FILE_NOT_FOUND', '文件标识无效')
        path = self.root / file_id
        if path.is_symlink():
            raise file_error('FILE_NOT_FOUND', '平台文件不可用')
        return path

    def _format(self, path, name):
        suffix = Path(name).suffix.lower()
        with path.open('rb') as source:
            signature = source.read(8)
        if suffix == '.pdf' and signature.startswith(b'%PDF-'):
            return 'pdf'
        if suffix == '.docx' and signature.startswith(b'PK\x03\x04'):
            try:
                with zipfile.ZipFile(path) as archive:
                    if {'[Content_Types].xml', 'word/document.xml'} <= set(archive.namelist()):
                        return 'docx'
            except (zipfile.BadZipFile, OSError):
                pass
        raise file_error('FILE_FORMAT_UNSUPPORTED', '仅支持扩展名与内容格式一致的 PDF/DOCX 文件')

    async def save(self, name, chunks):
        try:
            FileReference(file_id='file_' + '0' * 32, original_name=name, format='pdf', size=1, sha256='0' * 64)
        except ValueError:
            raise file_error('FILE_FORMAT_UNSUPPORTED', '原始文件名无效') from None
        file_id = 'file_' + uuid4().hex
        target, temporary = self._path(file_id), self.root / (file_id + '.part')
        digest, size = sha256(), 0
        try:
            with temporary.open('xb') as destination:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise file_error('FILE_TOO_LARGE', f'文件超过大小上限 {self.max_bytes} 字节')
                    destination.write(chunk)
                    digest.update(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if not size:
                raise file_error('FILE_FORMAT_UNSUPPORTED', '文件内容为空')
            format = self._format(temporary, name)
            reference = FileReference(file_id=file_id, original_name=name, format=format, size=size, sha256=digest.hexdigest())
            with self.lock:
                os.replace(temporary, target)
                document = {'reference': reference.model_dump(mode='json'), 'createdAt': time.time(), 'runIds': [], 'deleted': False}
                self.store.write([(self.collection, file_id, document)])
                self.items[file_id] = document
            return reference
        except OSError as exc:
            raise file_error('FILE_SAVE_FAILED', '磁盘空间不足' if exc.errno == errno.ENOSPC else '文件保存失败') from None
        finally:
            temporary.unlink(missing_ok=True)
            if file_id not in self.items:
                target.unlink(missing_ok=True)

    def resolve(self, reference, *, run_id=None):
        reference = FileReference.model_validate(reference)
        with self.lock:
            document = self.items.get(reference.file_id)
            if not document or document['deleted'] or (run_id and run_id not in document['runIds']):
                raise file_error('FILE_NOT_FOUND', '文件已删除、已过期或不属于当前任务')
            if not document['runIds'] and time.time() - document['createdAt'] >= self.pending_ttl:
                raise file_error('FILE_NOT_FOUND', '未提交的文件已过期，请重新选择')
            if FileReference.model_validate(document['reference']) != reference:
                raise file_error('FILE_REFERENCE_INVALID', '文件引用与平台保存记录不一致')
            path = self._path(reference.file_id)
            try:
                with path.open('rb') as source:
                    digest, size = sha256(), 0
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        size += len(chunk)
                if size != reference.size or digest.hexdigest() != reference.sha256:
                    raise file_error('FILE_REFERENCE_INVALID', '保存的文件内容已损坏')
            except OSError:
                raise file_error('FILE_NOT_FOUND', '保存的文件已删除或无法访问') from None
            return path

    def bindings(self, references, run_id):
        """调用方持有 lock，并与新任务在同一文档事务中保存。"""
        documents = []
        for reference in {r.file_id: r for r in references}.values():
            self.resolve(reference)
            old = self.items[reference.file_id]
            updated = {**old, 'runIds': [*old['runIds'], run_id]}
            documents.append((self.collection, reference.file_id, updated))
        return documents

    def accept_bindings(self, documents):
        for _, key, document in documents:
            self.items[key] = document

    def remove(self, file_id):
        with self.lock:
            document = self.items.get(file_id)
            if not document or document['deleted']:
                return
            if document['runIds']:
                raise file_error('FILE_REFERENCE_INVALID', '历史任务文件保留，不允许从上传区删除')
            updated = {**document, 'deleted': True}
            self.store.write([(self.collection, file_id, updated)])
            self.items[file_id] = updated
            self._path(file_id).unlink(missing_ok=True)

    def cleanup(self):
        now = time.time()
        for key, document in list(self.items.items()):
            if not document['runIds'] and now - document['createdAt'] >= self.pending_ttl:
                self.remove(key)
        for path in self.root.iterdir():
            if path.is_file() and now - path.stat().st_mtime >= self.pending_ttl:
                if path.name.endswith('.part') or path.name not in self.items or self.items[path.name]['deleted']:
                    path.unlink(missing_ok=True)


def file_references(schema, value):
    """按文件标注遍历实际输入，包含嵌套对象、数组和可空字段。"""
    refs = []
    def walk(node, data):
        if data is None:
            return
        if 'x-platform-file' in node:
            reference = FileReference.model_validate(data)
            if reference.format not in node['x-platform-file']['formats']:
                raise file_error('FILE_FORMAT_UNSUPPORTED', '文件格式不符合字段声明')
            refs.append(reference)
            return
        if '$ref' in node:
            walk(schema['$defs'][node['$ref'].split('/')[-1]], data)
        if isinstance(data, dict):
            for key, field in node.get('properties', {}).items():
                if key in data:
                    walk(field, data[key])
        if isinstance(data, list) and 'items' in node:
            for item in data:
                walk(node['items'], item)
        for option in node.get('anyOf', []) + node.get('oneOf', []) + node.get('allOf', []):
            walk(option, data)
    walk(schema, value)
    return refs
