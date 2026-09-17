from agent_platform.contracts.errors import ErrorResponse, PlatformError
from .models import GuidanceRequest, ModelRequest, ModelSummary, Output, Text


async def invoke(value, config, context):
    # 这是检查点：支持平台预算/取消检查，不会保存 message 为 UI 进度。
    await context.record_progress('prepare', '准备模型输入')
    normalized = await context.call_capability('normalize', Text(text=value.text))
    if not normalized.text.strip():
        raise PlatformError(ErrorResponse(
            code='CONTRACT_VALIDATION_ERROR', stage='sample.prepare',
            message='整理后的文本不能为空', field_path=['text'],
        ))

    guidance = ''
    if config.use_guidance:
        response = await context.call_capability('guidance', GuidanceRequest(topic=value.topic))
        guidance = response.instruction

    # 读取本次实例固定快照中的资源；不使用 __file__ 读取原始目录。
    prompt = context.read_resource('prompt.txt').decode('utf-8')
    instructions = '\n'.join([
        prompt, config.instruction, guidance,
        f'输出语言：{config.style.language}；关键词最多 {config.style.keyword_limit} 个。',
    ])
    response = await context.call_model('chat', ModelRequest(messages=[
        {'role': 'system', 'content': instructions},
        {'role': 'user', 'content': normalized.text},
    ], max_output_tokens=config.max_output_tokens))

    # ModelResponse 仅保证 output 是 JSON；业务结构和动态约束还须验证。
    try:
        summary = ModelSummary.model_validate(response.output, strict=True)
    except ValueError:
        raise PlatformError(ErrorResponse(
            code='OUTPUT_VALIDATION_ERROR', stage='sample.summary',
            message='模型输出不符合摘要契约',
        )) from None
    if len(summary.keywords) > config.style.keyword_limit:
        raise PlatformError(ErrorResponse(
            code='OUTPUT_VALIDATION_ERROR', stage='sample.summary',
            message='关键词数量超过节点配置的上限', field_path=['keywords'],
        ))

    await context.record_progress('validated', '业务输出校验完成')
    return Output(text=summary.text, keywords=summary.keywords, source_characters=len(normalized.text))
