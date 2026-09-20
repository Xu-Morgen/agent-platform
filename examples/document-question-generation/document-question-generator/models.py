"""文档出题契约；结构合法不代表知识与答案已经通过人工验收。"""
import re
from typing import Annotated, Literal

from pydantic import Field, model_validator
from agent_platform.contracts.base import StrictModel

NonBlank = Annotated[str, Field(min_length=1, pattern=r'\S')]


class Input(StrictModel):
    file_name: NonBlank
    text: NonBlank


class Essay(StrictModel):
    type: Literal['essay']
    stem: NonBlank
    reference_answer: NonBlank
    scoring_points: list[NonBlank] = Field(min_length=1)


class Options(StrictModel):
    A: NonBlank
    B: NonBlank
    C: NonBlank
    D: NonBlank

    @model_validator(mode='after')
    def distinct(self):
        values = [re.sub(r'\s+', ' ', value).strip().casefold() for value in (self.A, self.B, self.C, self.D)]
        if len(set(values)) != 4:
            raise ValueError('四个选项不得重复')
        return self


class SingleChoice(StrictModel):
    type: Literal['single_choice']
    stem: NonBlank
    options: Options
    reference_answer: Literal['A', 'B', 'C', 'D']
    explanation: NonBlank


class FillBlank(StrictModel):
    type: Literal['fill_blank']
    stem: Annotated[str, Field(min_length=1, pattern=r'____')]
    reference_answers: list[NonBlank] = Field(min_length=1)

    @model_validator(mode='after')
    def blanks_match(self):
        blanks = re.findall(r'_+', self.stem)
        if any(blank != '____' for blank in blanks) or len(blanks) != len(self.reference_answers):
            raise ValueError('每个空位必须恰好四个下划线，答案数量与空位数量一致')
        return self


Question = Annotated[Essay | SingleChoice | FillBlank, Field(discriminator='type')]


class Output(StrictModel):
    questions: list[Question] = Field(min_length=3, max_length=3)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(core_schema)
        questions = schema['properties']['questions']
        # 复用联合类型生成的引用，Schema 同时表达题数和固定题型顺序。
        mapping = questions['items']['discriminator']['mapping']
        questions['prefixItems'] = [{'$ref': mapping[kind]} for kind in ('essay', 'single_choice', 'fill_blank')]
        return schema

    @model_validator(mode='after')
    def order(self):
        if [question.type for question in self.questions] != ['essay', 'single_choice', 'fill_blank']:
            raise ValueError('必须依次包含论述题、单选题、填空题各一道')
        return self
