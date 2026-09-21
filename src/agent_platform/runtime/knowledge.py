"""提交固定引用；执行时只向已绑定任务提供修订范围内的访问能力。"""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import shutil
from pydantic import ValidationError
from ..contracts.knowledge import (
    KnowledgeReference, FixedKnowledgeReference, KnowledgePageRequest,
    DocumentReadRequest, EvidenceRegistration, EvidenceRecord,
)
from ..repositories.knowledge import knowledge_error


def bind_knowledge(schema, value, repository):
    value = deepcopy(value)
    bindings = []
    def walk(node, data):
        if data is None:
            return
        if node.get('x-platform-knowledge'):
            if repository is None:
                raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '知识库存储不可用')
            fixed = repository.resolve(KnowledgeReference.model_validate(data), active=True)
            data.clear()
            data.update(fixed.model_dump(mode='json', by_alias=True))
            if fixed not in bindings:
                bindings.append(fixed)
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
    return value, bindings


class TaskKnowledgeAccess:
    def __init__(self, repository, runs, run_id, node_id, resource_digest, directory):
        self.repository, self.runs, self.run_id = repository, runs, run_id
        self.node_id, self.resource_digest, self.directory = node_id, resource_digest, Path(directory)

    def resolve(self, reference):
        matches = [item for item in self.runs.get(self.run_id).knowledge_bindings
                   if item.knowledge_id == reference.knowledge_id
                   and (reference.revision_id is None or item.revision_id == reference.revision_id)]
        if len(matches) != 1:
            raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '引用不属于当前任务固定修订，或存在多个修订需要明确指定')
        return matches[0]

    async def __call__(self, operation, payload):
        from .boundary import checkpoint
        await checkpoint('knowledge_access', self.node_id)
        run = self.runs.get(self.run_id)
        if run.status != 'running' or run.cancel_requested:
            raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '任务已终止或请求取消，不再接受知识库访问')
        if self.repository is None:
            raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '知识库上下文不可用')
        try:
            if operation == 'resolve':
                result = self.resolve(KnowledgeReference.model_validate(payload))
            elif operation == 'list':
                request = KnowledgePageRequest.model_validate(payload)
                self.resolve(request.reference)
                result = self.repository.page(request)
            elif operation in ('metadata', 'file'):
                request = DocumentReadRequest.model_validate(payload)
                self.resolve(request.reference)
                result = self.repository.metadata(request)
                if operation == 'file':
                    # 给受信任资源调用专用副本，原件位置与存储结构不外泄；调用结束即清理。
                    source = self.repository.original(request)
                    target = self.directory / (request.version_id + '.docx')
                    shutil.copyfile(source, target)
                    await checkpoint('knowledge_read', self.node_id)
                    return str(target)
            elif operation == 'record':
                request = EvidenceRegistration.model_validate(payload)
                request.verify_selection()
                self.resolve(request.reference)
                members = set(self.repository.revision(request.reference).versions)
                if not set(request.scanned_versions) <= members:
                    raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '扫描版本不属于当前任务修订')
                for item in request.candidates:
                    metadata = self.repository.metadata(DocumentReadRequest(reference=request.reference, version_id=item.version_id))
                    if metadata.document_id != item.document_id:
                        raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '证据文档身份与版本不一致')
                result = EvidenceRecord(**request.model_dump(), record_id='ev_' + uuid4().hex,
                    node_id=self.node_id, resource_digest=self.resource_digest)
                self.runs.append_evidence(self.run_id, result)
            else:
                raise knowledge_error('KNOWLEDGE_SCOPE_ERROR', '未知知识库操作')
        except ValueError as exc:
            if not isinstance(exc, ValidationError):
                raise knowledge_error('CONTRACT_VALIDATION_ERROR', str(exc)) from None

            from ..validation_issues import validation_exception
            raise validation_exception(exc, stage='knowledge.request') from None
        return result.model_dump(mode='json', by_alias=True)
