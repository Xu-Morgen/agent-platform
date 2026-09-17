"""Ollama 原生 chat 的首期能力声明与供应商计量转换。"""
from ..contracts.models import ModelCapabilities, ModelUsage
from ..contracts.errors import ErrorResponse, PlatformError

OLLAMA_CAPABILITIES = ModelCapabilities(
    protocol='ollama-chat', input_preflight='unsupported', response_usage='exact',
    missing_usage='unsupported', output_limit=True, hidden_tokens_verified=False,
    strict_total_limit=False, closes_local_transport=True)


def ollama_usage(response):
    keys = ('prompt_eval_count', 'eval_count')
    if any(key not in response for key in keys):
        return ModelUsage(quality='unsupported', source='ollama:usage_missing')
    values = [response[key] for key in keys]
    if any(type(value) is not int or value < 0 for value in values):
        raise PlatformError(ErrorResponse(code='OUTPUT_VALIDATION_ERROR', stage='model.usage', message='模型用量字段无效'), 502)
    return ModelUsage(input_tokens=values[0], output_tokens=values[1], quality='exact',
                      source='ollama:prompt_eval_count+eval_count')
