"""Pydantic request/response schemas for the /module endpoint."""

from typing import Optional

from pydantic import BaseModel, Field


class DetectedProcessIn(BaseModel):
    process: str
    position: str = ""
    detail: str = ""
    target_sound: Optional[str] = None


class ModuleRequest(BaseModel):
    age: int = Field(ge=2, le=12, description="Child's age in years")
    processes: list[DetectedProcessIn] = Field(default_factory=list)
    pcc: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class PracticeItemOut(BaseModel):
    text: str
    target_sound: str
    position: str = ""


class LevelOut(BaseModel):
    level: str
    items: list[PracticeItemOut]


class ModuleResponse(BaseModel):
    module_id: str
    focus_sounds: list[str]
    focus_processes: list[str]
    outline_id: str
    outline_title: str
    levels: list[LevelOut]
    rationale: str
    generated_by: str
    warning: Optional[str] = None
