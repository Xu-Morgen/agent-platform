"""知识库页面只提供标准预览输入；候选必须静态接受该输入并返回正文片段。"""
from .contracts.base import export_schema
from .contracts.retrieval import DocumentPreviewRequest, DocumentPreviewService, ParsedCorpus
from .contracts.errors import PlatformError
from .flows.compatibility import assignable, Incompatible, resolve
from .flows.configuration import validate_configurations


def preview_services(services, environments):
    request_schema = export_schema(DocumentPreviewRequest)
    # 页面只提交知识库与版本；不能用未发送的可选 limits 满足服务额外必填字段。
    request_schema['properties'] = {key: value for key, value in request_schema['properties'].items()
                                    if key in request_schema['required']}
    output_schema = export_schema(ParsedCorpus)
    result = []
    for service in services.list():
        try:
            snapshot = services.resolve_current(service.service_id)
        except PlatformError as exc:
            if exc.error.code == 'VERSION_CONFLICT':
                continue
            raise
        try:
            input_schema = snapshot.schema['input']
            root = resolve(input_schema, input_schema)
            knowledge = resolve(root.get('properties', {}).get('knowledge', {}), input_schema)
            if not knowledge.get('x-platform-knowledge'):
                continue
            assignable(request_schema, input_schema)
            assignable(snapshot.schema['output'], output_schema)
        except Incompatible:
            continue
        if not validate_configurations(snapshot.draft, snapshot.catalog, environments).valid:
            continue
        result.append(DocumentPreviewService(service_id=service.service_id,
            instance_id=snapshot.instance_id, name=service.name, version=service.current.version))
    return result
