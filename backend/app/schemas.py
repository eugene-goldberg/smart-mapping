from typing import Any, Optional
from pydantic import BaseModel


class MappingCreate(BaseModel):
    positionId: int
    taxonomyConceptId: int


class SuccessEnvelope(BaseModel):
    success: bool = True


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: str
