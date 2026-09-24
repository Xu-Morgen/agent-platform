"""成功与失败 HTTP 响应共用的供应商用量校验。"""
from ..contracts.models import ModelUsage
from ..contracts.errors import ErrorResponse, PlatformError


class ModelCallError(PlatformError):
    """失败响应仍保留供应商用量。"""
    def __init__(self, error, usage=None):
        super().__init__(error, 502)
        self.usage = usage


def response_usage(response):
    usage = response.get('usage') if isinstance(response, dict) else None
    if usage is None:
        return ModelUsage(quality='unsupported', source='openai-chat:usage_missing')
    if not isinstance(usage, dict) or any(type(usage.get(key)) is not int or usage[key] < 0
            for key in ('prompt_tokens', 'completion_tokens')):
        raise ModelCallError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='model.usage',
                                          message='模型用量字段无效'))
    if 'total_tokens' in usage and (type(usage['total_tokens']) is not int or
            usage['total_tokens'] != usage['prompt_tokens'] + usage['completion_tokens']):
        raise ModelCallError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='model.usage',
                                          message='模型用量总数不一致'))
    # completion_tokens 已含供应商报告的推理消耗，不再叠加明细。
    return ModelUsage(input_tokens=usage['prompt_tokens'], output_tokens=usage['completion_tokens'],
                      quality='exact', source='openai-chat:prompt_tokens+completion_tokens')
