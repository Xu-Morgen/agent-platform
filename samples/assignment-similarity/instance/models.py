from agent_platform.contracts.models import ModelRequest, ModelResponse
from .contracts import SimilarityInput, SimilarityReport, QuantitativeReport, QualitativeReport
from .preprocessing import PreparedTexts


class State(SimilarityInput):
    prepared: PreparedTexts | None = None
    quantitative: QuantitativeReport | None = None
    qualitative: QualitativeReport | None = None
    report: SimilarityReport | None = None
