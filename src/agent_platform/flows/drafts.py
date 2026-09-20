"""会话内编辑内容及全流程预检；不编译、分配实例或调用模型。"""
from uuid import uuid4
from pydantic import ValidationError
from ..contracts.drafts import DraftDocument
from ..contracts.flows import FlowDraft
from ..contracts.errors import PlatformError, ValidationIssue
from ..registry.validation import invalid
from ..validation_issues import issues_from_errors
from .validation import validate_flow, ValidationResult
from .configuration import validate_configurations


class DraftRepository:
    def __init__(self, store=None):
        from ..storage import MemoryStore
        self.store = store or MemoryStore()
        self._items = {key: DraftDocument.model_validate(value).model_dump_json()
                       for key, value in self.store.read("drafts").items()}

    def save(self, request, draft_id=None):
        if draft_id is not None and draft_id not in self._items:
            raise invalid('草稿不存在', ['draftId'], code='RECORD_NOT_FOUND')
        draft_id = draft_id or 'draft_' + uuid4().hex
        content = {**request.content, 'draftId': draft_id}
        document = DraftDocument(draft_id=draft_id, content=content)
        self.store.write([("drafts", draft_id, document.model_dump(mode="json"))])
        self._items[draft_id] = document.model_dump_json()
        return self.get(draft_id)

    def get(self, draft_id):
        if draft_id not in self._items:
            raise invalid('草稿不存在', ['draftId'], code='RECORD_NOT_FOUND')
        return DraftDocument.model_validate_json(self._items[draft_id])

    def list(self):
        return [self.get(key) for key in self._items]


def preflight(content, catalog, environments):
    try:
        draft = FlowDraft.model_validate(content)
    except ValidationError as exc:
        issues = issues_from_errors(exc.errors(), stage='flow.structure')
        # Pydantic 判别联合的 loc 带类型标签；跳过标签找到实际节点。
        for issue in issues:
            current = content
            for part in issue.field_path:
                if isinstance(current, dict):
                    if 'nodeId' in current and isinstance(current['nodeId'], str):
                        issue.node_id = current['nodeId']
                    if part in current:
                        current = current[part]
                elif isinstance(current, list) and type(part) is int and 0 <= part < len(current):
                    current = current[part]
        return ValidationResult(valid=False, issues=issues)
    issues = validate_flow(draft, catalog).issues
    issues.extend(validate_configurations(draft, catalog, environments).issues)
    try:
        input_contract = catalog.contract(draft.input_contract)
        for index, example in enumerate(draft.examples):
            try:
                input_contract.adapter.validate_python(example.input, strict=True)
            except ValidationError as exc:
                issues.extend(issues_from_errors(exc.errors(), stage='flow.example', prefix=['examples', index, 'input']))
            except PlatformError as exc:
                # 子进程适配器投影后的校验错误仍须定位到当前示例，不能当资源缺失忽略。
                projected = exc.error.issues or [ValidationIssue(reason=exc.error.message,
                    field_path=exc.error.field_path or [])]
                issues.extend(issue.model_copy(update={'stage': 'flow.example',
                    'field_path': ['examples', index, 'input', *issue.field_path]}) for issue in projected)
    except PlatformError:
        pass  # 资源错误已经由端口检查记录，避免重复。
    return ValidationResult(valid=not issues, issues=issues)
