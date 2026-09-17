"""真实 Ollama Chat 协议；不包含供应商 SDK 或自动重试。"""
import json
from .http import JsonTransport
from .model_protocol import OLLAMA_CAPABILITIES, ollama_usage
from ..contracts.models import ModelRequest, ModelResponse
from ..contracts.errors import ErrorResponse, PlatformError


class ModelCallError(PlatformError):
    """保留失败响应的计量，供任务步骤及后续预算账本使用。"""
    def __init__(self, error, usage=None):
        super().__init__(error, 502)
        self.usage = usage


class OllamaAdapter:
    capabilities = OLLAMA_CAPABILITIES

    def __init__(self, credentials):
        self.transport = JsonTransport(credentials)

    async def preflight(self, connection, request):
        from ..contracts.models import ModelUsage
        return ModelUsage(quality='unsupported', source='ollama:no_input_preflight')

    async def invoke(self, connection, request):
        request = ModelRequest.model_validate(request)
        payload = {'model': connection.model,
                   'messages': [m.model_dump() for m in request.messages],
                   'stream': False, 'format': 'json',
                   'options': {'num_predict': request.max_output_tokens}}
        response = await self.transport.request(connection, 'POST', connection.base_url.rstrip('/') + '/api/chat', payload, kind='model')
        usage = ollama_usage(response) if isinstance(response, dict) else None
        def invalid():
            return ModelCallError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='model.output',
                                  message='模型响应未完成或输出不是有效 JSON'), usage)
        if not isinstance(response, dict) or response.get('done') is not True or response.get('done_reason') != 'stop' or 'error' in response:
            raise invalid()
        message = response.get('message')
        if not isinstance(message, dict) or message.get('role') != 'assistant' or not isinstance(message.get('content'), str) or message.get('tool_calls'):
            raise invalid()
        try:
            # 标准 JSON 不接受 NaN/Infinity，也不猜测 Markdown 中的片段。
            def invalid_constant(value):
                raise ValueError()
            output = json.loads(message['content'], parse_constant=invalid_constant)
            return ModelResponse(output=output, usage=usage)
        except ValueError:
            raise invalid() from None

    async def close(self):
        await self.transport.close()
