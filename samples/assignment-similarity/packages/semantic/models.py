from pydantic import Field
from agent_platform.contracts.packages import PackageBudget
from agent_platform.contracts.models import ModelRequest, ModelResponse
from .contracts import SimilarityInput, QualitativeReport


class Config(PackageBudget):
    max_output_tokens: int = Field(default=4096, gt=0)
