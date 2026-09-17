"""完整通用块：嵌套输入、默认值、枚举、字段约束与明确输出。

所有可调整选项都是输入的一部分，可由服务输入或接线常量提供。
本例不需要外部 I/O，因此使用同步函数；异步函数也受加载器支持。
"""
import re
from typing import Literal

from pydantic import Field
from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel


class Options(StrictModel):
    trim_edges: bool = Field(default=True, description='去掉首尾空白')
    collapse_spaces: bool = Field(default=True, description='将连续空白合并为一个空格，包含换行')
    letter_case: Literal['preserve', 'lower', 'upper'] = Field(default='preserve', description='字母大小写转换')
    prefix: str = Field(default='', max_length=20, description='在处理后的文本前添加前缀')


class Input(StrictModel):
    text: str = Field(min_length=1, max_length=10000, description='待处理文本')
    options: Options = Field(default_factory=Options, description='本次调用的处理选项')


class Output(StrictModel):
    text: str = Field(description='处理结果；纯空白输入去除后允许为空')
    character_count: int = Field(ge=0, description='Python len(text)，按 Unicode 码点计数')
    changed: bool = Field(description='最终文本是否与原始输入不同')


@block(
    id='sample-normalize',
    version='1.0.0',
    name='可配置文本整理',
    description='依次去掉首尾空白、合并空白、转换大小写、添加前缀，并输出字符数。',
    dependencies=[],  # 标准库与平台内置的 pydantic 无需额外声明。
)
def normalize(value: Input) -> Output:
    text = value.text.strip() if value.options.trim_edges else value.text
    if value.options.collapse_spaces:
        text = re.sub(r'\s+', ' ', text)
    if value.options.letter_case == 'lower':
        text = text.lower()
    elif value.options.letter_case == 'upper':
        text = text.upper()
    text = value.options.prefix + text
    return Output(text=text, character_count=len(text), changed=text != value.text)
