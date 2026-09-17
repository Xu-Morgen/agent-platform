from agent_platform.adapters.model_protocol import OLLAMA_CAPABILITIES, ollama_usage
from agent_platform.contracts.models import ModelRequest, ModelResponse
request = ModelRequest(messages=[{'role':'user','content':'返回合成 JSON'}], max_output_tokens=32)
usage = ollama_usage({'prompt_eval_count':7,'eval_count':3})
assert usage.quality == 'exact' and usage.input_tokens + usage.output_tokens == 10
missing = ollama_usage({})
assert missing.quality == 'unsupported' and missing.input_tokens is None
assert not OLLAMA_CAPABILITIES.strict_total_limit
assert OLLAMA_CAPABILITIES.input_preflight == 'unsupported'
assert ModelResponse(output={'text':'合成'}, usage=missing).output == {'text':'合成'}
print('模型协议：有效 usage 精确记录，缺失计量标为不支持，不声称严格预算保证')
