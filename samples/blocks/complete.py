"""最完整通用块：API 查询、响应校验、嵌套选项与文本处理。

文本处理选项是完整输入的一部分，由服务输入或上一层通用块提供。
API 的 Base URL、凭据与超时由绑定环境提供，请求路径由平台节点配置。
示例使用 GET 并传入 query 参数，响应为 {"text": "..."}；路径不写入块代码。
"""
import re
from typing import Literal

from pydantic import Field
from agent_platform.blocks import BlockAPI, BlockContext, block
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.files import TaskFile


class Options(StrictModel):
    trim_edges: bool = Field(default=True, description='去掉首尾空白')
    collapse_spaces: bool = Field(default=True, description='将连续空白合并为一个空格，包含换行')
    letter_case: Literal['preserve', 'lower', 'upper'] = Field(default='preserve', description='字母大小写转换')
    prefix: str = Field(default='', max_length=20, description='在处理后的文本前添加前缀')


class Input(StrictModel):
    query: str = Field(min_length=1, max_length=10000, description='发送给 API 的查询文本')
    options: Options = Field(default_factory=Options, description='本次调用的处理选项')
    attachment: TaskFile | None = Field(default=None, description='可选任务附件；由任务页面选择并保存')


class APIResponse(StrictModel):
    text: str = Field(min_length=1, max_length=10000, description='API 返回的待处理文本')


class Output(StrictModel):
    text: str = Field(description='处理结果；纯空白输入去除后允许为空')
    character_count: int = Field(ge=0, description='Python len(text)，按 Unicode 码点计数')
    changed: bool = Field(description='最终文本是否与 API 返回的原始文本不同')


@block(
    id='sample-normalize',
    version='1.0.0',
    name='API 查询与文本整理',
    description='查询 API 并校验响应，再按嵌套选项整理文本，输出字符数与变化标记。',
    api=True,
    dependencies=[],  # 标准库与平台内置的 pydantic 无需额外声明。
    dependencySources=[],  # 首期仅接受固定 HTTPS 索引或带 SHA-256 的 wheel 来源。
    models=[],  # 实际模型填写 name/version/url/sha256/filename，不能填写猜测的摘要。
)
async def normalize(value: Input, *, api: BlockAPI, context: BlockContext) -> Output:
    if value.attachment is not None:
        # 校验属于当前任务的已保存副本；此文本模板不解析 PDF/DOCX 内容。
        context.file(value.attachment)
    response = await api.request('GET', {'query': value.query}, response_type=APIResponse)
    text = response.text.strip() if value.options.trim_edges else response.text
    if value.options.collapse_spaces:
        text = re.sub(r'\s+', ' ', text)
    if value.options.letter_case == 'lower':
        text = text.lower()
    elif value.options.letter_case == 'upper':
        text = text.upper()
    text = value.options.prefix + text
    return Output(text=text, character_count=len(text), changed=text != response.text)
