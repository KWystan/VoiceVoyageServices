"""HTTP adapter for the dynamic modules service — thin, no business logic."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.schemas import LevelOut, ModuleRequest, ModuleResponse, PracticeItemOut
from application.module_builders import NoOutlineError
from application.module_service import ModuleService, NoFindingsError
from config import config

logger = logging.getLogger(__name__)

router = APIRouter()


def make_service() -> ModuleService:
    from infrastructure.mock_data import MockOutlines, MockWordBank
    return ModuleService(outlines=MockOutlines(), bank=MockWordBank())


@router.post("/module", response_model=ModuleResponse)
def create_module(request: ModuleRequest) -> ModuleResponse:
    """Build a personalized practice module for the child's findings."""
    from domain.models import AssessmentFindings, DetectedProcess

    findings = AssessmentFindings(
        age=request.age,
        processes=tuple(
            DetectedProcess(
                process=p.process,
                position=p.position,
                detail=p.detail,
                target_sound=p.target_sound,
            )
            for p in request.processes
        ),
        pcc=request.pcc,
    )

    service = make_service()
    try:
        module = service.build_module(findings)
    except (NoFindingsError, NoOutlineError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ModuleResponse(
        module_id=module.module_id,
        focus_sounds=[s.sound for s in module.focus_sounds],
        focus_processes=module.focus_processes,
        outline_id=module.outline_id,
        outline_title=module.outline_title,
        levels=[
            LevelOut(
                level=level.value,
                items=[
                    PracticeItemOut(
                        text=item.text,
                        target_sound=item.target_sound,
                        position=item.position,
                    )
                    for item in items
                ],
            )
            for level, items in module.levels.items()
        ],
        rationale=module.rationale,
        generated_by=module.generated_by,
        warning=module.warning,
    )
