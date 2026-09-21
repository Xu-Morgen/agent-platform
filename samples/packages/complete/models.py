from typing import Annotated, Literal
from pydantic import Field
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput


class Input(StrictModel):
    """上游准备的待摘要正文。"""
    text: str = Field(min_length=1, max_length=10000, description='由上游块准备的文本')


class Style(StrictModel):
    """控制摘要的输出语言。"""
    language: Literal['zh', 'en'] = Field(default='zh', description='摘要输出语言')


class Config(StrictModel):
    """摘要节点参数：控制要求和语言，不携带模型连接或凭据。"""
    instruction: str = Field(default='准确概括事实，不补充原文之外的信息。', min_length=1, description='模型生成摘要时遵循的业务要求，每个包节点独立配置。')
    style: Style = Field(default_factory=Style, description='摘要风格配置，当前包含输出语言。')


class Output(StrictModel):
    """摘要与关键词，作为完整对象交给下一步。"""
    text: str = Field(min_length=1, description='模型生成的摘要')
    keywords: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=3, description='从原文中提取的 1～3 个非空关键词，用于概览摘要主题。')


class Entry(NodeInput[Input, tuple[Annotated[Input, Field(description="摘要所依据的原始文本，用于核对摘要与关键词中的事实，避免引入原文未提供的信息。")]]]):
    """主数据为待摘要文本；唯一参考为原始文本，数量与位置固定。"""
