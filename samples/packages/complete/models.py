from typing import Annotated, Literal

from pydantic import Field, field_validator
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.models import ModelRequest, ModelResponse
from agent_platform.contracts.packages import PackageBudget


class Text(StrictModel):
    """块能力契约，与 blocks/minimal.py 的 Text 结构一致；包可独立复制。"""
    text: str


class Input(StrictModel):
    text: str = Field(min_length=1, max_length=10000, description='待概括文本')
    topic: str = Field(default='general', min_length=1, description='向指导 API 查询的主题')


class GuidanceRequest(StrictModel):
    topic: str = Field(min_length=1)


class GuidanceResponse(StrictModel):
    instruction: str = Field(min_length=1, description='API 返回的可信指导；不接受额外包装字段')


class Style(StrictModel):
    language: Literal['zh', 'en'] = Field(default='zh', description='摘要输出语言')
    keyword_limit: int = Field(default=3, ge=1, le=10, description='关键词数量上限')


class Config(PackageBudget):
    instruction: str = Field(default='准确概括事实，不补充原文之外的信息。', min_length=1, description='实例级附加指令')
    max_output_tokens: int = Field(default=512, ge=64, le=4096, description='单次模型请求输出上限，平台可按余额收紧')
    use_guidance: bool = Field(default=False, description='是否实际调用指导 API；关闭仍须提供声明的能力绑定')
    style: Style = Field(default_factory=Style, description='嵌套输出风格配置')

    @field_validator('instruction')
    @classmethod
    def reject_blank_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('instruction 不能全部为空白')
        return value


class ModelSummary(StrictModel):
    text: str = Field(min_length=1)
    keywords: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=10)


class Output(StrictModel):
    text: str = Field(min_length=1, description='模型生成的摘要')
    keywords: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=10)
    source_characters: int = Field(ge=1, description='确定性计算的整理后原文字符数')
