"""完整独立契约：按 symbol 分别加载 Input 或 Output。

演示嵌套、枚举、可空、默认值及校验钩子；不执行模型或业务请求。
自定义校验不能只靠 JSON Schema 证明等价，接线时需注意契约身份。
"""
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.files import TaskFile

ItemId = Annotated[str, Field(pattern=r'^[a-z][a-z0-9-]{0,31}$')]
Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Item(StrictModel):
    item_id: ItemId = Field(description='批次内唯一的条目标识')
    text: str = Field(min_length=1, max_length=2000, description='非纯空白文本')

    @field_validator('text')
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('text 不能全部为空白')
        return value  # 校验而不隐式改变业务文本。


class Input(StrictModel):
    attachment: TaskFile | None = Field(default=None, description='可选已保存任务附件；页面根据契约显示选择控件')
    items: list[Item] = Field(min_length=1, max_length=20, description='待处理条目')
    note: str | None = Field(description='必填但可为 null；没有默认值')
    language: Literal['zh', 'en'] = Field(default='zh', description='输出语言')
    min_score: Score = Field(default=0.0, description='允许的最低分数')
    max_score: Score = Field(default=1.0, description='允许的最高分数')
    labels: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list, max_length=5, description='可省略的标签列表')

    @model_validator(mode='after')
    def check_batch(self) -> 'Input':
        if self.min_score > self.max_score:
            raise ValueError('minScore 不能大于 maxScore')
        ids = [item.item_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError('itemId 不能重复')
        return self


class Result(StrictModel):
    item_id: ItemId
    score: Score
    accepted: bool


class Output(StrictModel):
    results: list[Result] = Field(min_length=1, max_length=20, description='由执行节点实际生成的结果')
    summary: str = Field(min_length=1, description='结果说明')
    reviewer_note: str | None = Field(default=None, description='可省略，也可以显式为 null')
