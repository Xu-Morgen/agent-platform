"""OpenAI 兼容 Chat Completions；一次非流式 JSON 交互，无重试。"""
import json
from .http import JsonTransport
from ..contracts.models import ModelRequest, ModelResponse
from ..contracts.errors import ErrorResponse
from .model_usage import ModelCallError, response_usage


class OpenAIChatAdapter:
    def __init__(self, credentials):
        self.transport = JsonTransport(credentials)

    async def invoke(self, connection, request):
        request = ModelRequest.model_validate(request)
        payload = {'model':connection.model, 'messages':[m.model_dump() for m in request.messages],
                   'stream':False, connection.output_token_parameter:request.max_output_tokens}
        if connection.json_mode:
            payload['response_format'] = {'type':'json_object'}
        response = await self.transport.request(connection, 'POST',
            connection.base_url.rstrip('/') + '/chat/completions', payload, kind='model')
        usage = response_usage(response)
        def invalid():
            return ModelCallError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='model.output',
                message='模型响应未完成、拒绝回答或输出不是有效 JSON'), usage)
        if not isinstance(response, dict) or 'error' in response:
            raise invalid()
        choices = response.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise invalid()
        choice = choices[0]
        message = choice.get('message')
        if (choice.get('finish_reason') != 'stop' or not isinstance(message, dict)
                or message.get('role') != 'assistant' or not isinstance(message.get('content'), str)
                or message.get('refusal') or message.get('tool_calls') or message.get('function_call')):
            raise invalid()
        try:
            def invalid_constant(value):
                raise ValueError()
            output = json.loads(message['content'], parse_constant=invalid_constant)
            return ModelResponse(output=output, usage=usage)
        except ValueError:
            raise invalid() from None

    async def close(self):
        await self.transport.close()
