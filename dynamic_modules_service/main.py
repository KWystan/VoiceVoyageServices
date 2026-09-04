"""FastAPI adapter for validated, text-only dynamic learning modules."""

import logging
import os
import sys
from functools import lru_cache
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

_SERVICE_ROOT = os.path.dirname(os.path.abspath(__file__))
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)


def _load_dotenv(path=None) -> None:
    candidates = [
        path,
        os.path.join(_SERVICE_ROOT, ".env"),
        os.path.join(os.path.dirname(_SERVICE_ROOT), ".env"),
    ]
    selected = next(
        (candidate for candidate in candidates if candidate and os.path.exists(candidate)),
        None,
    )
    if selected is None:
        return
    with open(selected, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

try:
    from dynamic_modules_service.config import config
except ImportError:
    from config import config
from models import AssessmentFindings, DetectedProcess
from security import require_authenticated_user
from service import ModuleService, NoContentError, NoFindingsError, NoOutlineError

config.validate_runtime()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class DetectedProcessPayload(BaseModel):
    """Strict form-JSON shape accepted from the phoneme client."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    process: str = Field(min_length=1, max_length=80)
    position: str = Field(default="", max_length=40)
    detail: str = Field(default="", max_length=300)
    target_sound: str | None = Field(default=None, max_length=24)


_processes_adapter = TypeAdapter(list[DetectedProcessPayload])

app = FastAPI(title="Dynamic Modules Service", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)


@lru_cache(maxsize=1)
def make_service() -> ModuleService:
    """Load and validate immutable content once per process."""

    from data import GradeDocuments, MockOutlines, MockWordBank, ModuleCatalog

    bank = MockWordBank()
    module_catalog = ModuleCatalog()
    module_catalog.validate_layout()
    return ModuleService(
        outlines=MockOutlines(bank),
        bank=bank,
        grade_documents=GradeDocuments(),
        module_catalog=module_catalog,
    )


@app.post("/module")
def create_module(
    age: Annotated[int, Form(ge=4, le=8)],
    processes: Annotated[str, Form(min_length=2)],
    grade: Annotated[str | None, Form(max_length=32)] = None,
    _user_id: Annotated[
        str | None, Depends(require_authenticated_user)
    ] = None,
):
    """Build a module from age, grade, and detected-process JSON."""

    if len(processes.encode("utf-8")) > config.max_processes_json_bytes:
        raise HTTPException(status_code=413, detail="Detected-process payload is too large.")
    try:
        process_payloads = _processes_adapter.validate_json(processes)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail="processes must be a JSON array of valid detected-process objects.",
        ) from exc
    if len(process_payloads) > config.max_detected_processes:
        raise HTTPException(
            status_code=400,
            detail=f"At most {config.max_detected_processes} detected processes are allowed.",
        )

    findings = AssessmentFindings(
        age=age,
        grade=grade,
        processes=tuple(
            DetectedProcess(
                process=payload.process,
                position=payload.position,
                detail=payload.detail,
                target_sound=payload.target_sound,
            )
            for payload in process_payloads
        ),
    )
    try:
        module = make_service().build_module(findings)
    except (NoFindingsError, NoOutlineError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    atypical_processes = {
        "Initial Consonant Deletion",
        "Medial Consonant Deletion",
        "Backing",
        "Liquidization",
        "Frication",
        "Denasalization",
    }
    return {
        "module_id": module.module_id,
        "grade": module.grade,
        "focus_sounds": [sound.sound for sound in module.focus_sounds],
        "focus_processes": module.focus_processes,
        "outline_id": module.outline_id,
        "outline_title": module.outline_title,
        "levels": [
            {
                "level": level.value,
                "items": [
                    {
                        "text": item.text,
                        "assessment_text": item.text,
                        "target_sound": item.target_sound,
                        "position": item.position,
                        "language": item.language,
                        "language_variety": item.language_variety,
                    }
                    for item in items
                ],
            }
            for level, items in module.levels.items()
        ],
        "rationale": module.rationale,
        "generated_by": module.generated_by,
        "review_recommended": any(
            process in atypical_processes for process in module.focus_processes
        ),
        # Backward-compatible internal routing alias; not a diagnosis.
        "atypical_flag": any(
            process in atypical_processes for process in module.focus_processes
        ),
        "warning": module.warning,
    }


@app.get("/")
def root():
    return {
        "service": "Voice Voyage Dynamic Modules Service",
        "status": "online",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "dynamic-modules",
        "provider": config.llm_provider,
        "model": config.llm_model,
    }


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.host,
        port=int(os.environ.get("PORT", config.port)),
    )
