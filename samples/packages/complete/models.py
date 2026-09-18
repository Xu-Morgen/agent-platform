from typing import Annotated, Literal
from pydantic import Field
from agent_platform.contracts.base import StrictModel


class Input(StrictModel):
    text: str = Field(min_length=1, max_length=10000, description='由上游块准备的文本')


class Style(StrictModel):
    language: Literal['zh', 'en'] = Field(default='zh', description='摘要输出语言')


class Config(StrictModel):
    instruction: str = Field(default='准确概括事实，不补充原文之外的信息。', min_length=1)
    style: Style = Field(default_factory=Style)


class Output(StrictModel):
    text: str = Field(min_length=1, description='模型生成的摘要')
    keywords: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=3)
