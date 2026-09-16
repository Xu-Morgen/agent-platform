from typing import Literal
from .base import StrictModel


class HealthResponse(StrictModel):
    status: Literal['ready']
