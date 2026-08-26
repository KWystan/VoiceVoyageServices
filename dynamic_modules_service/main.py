"""Dynamic Modules Service — FastAPI app (port 8002).

POST /module — builds a personalized practice module from the child's
AGE and the DETECTED PHONEME PROCESSES (multiple) returned by the
phoneme service.  OpenCode Zen (DeepSeek V4 Flash Free) makes the
humanlike decision; rule-based fallback when the LLM is unavailable.
"""

import sys
import subprocess
import logging

# Windows UTF-8 workaround (IPA/JSON payloads break without it)
if not sys.flags.utf8_mode:
    subprocess.call([sys.executable, "-X", "utf8"] + sys.argv)
    sys.exit()

import json
import os
import uvicorn

from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _load_dotenv(path=None) -> None:
    """Minimal .env loader — mirrors docker-compose ``env_file`` behavior
    so local runs see ZEN_API_KEY exactly like the container does.

    Checks the service directory first, then the repo root (where
    docker-compose reads ``env_file: .env`` from)."""
    service_root = os.path.dirname(os.path.abspath(__file__))
    candidates = [path, os.path.join(service_root, ".env"),
                  os.path.join(os.path.dirname(service_root), ".env")]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            path = candidate
            break
    else:
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and not os.environ.get(key):
                os.environ[key] = value


_load_dotenv()

try:
    from dynamic_modules_service.config import config
except ImportError:
    from config import config
from models import AssessmentFindings, DetectedProcess
from service import ModuleService, NoFindingsError, NoOutlineError

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(title="Dynamic Modules Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def make_service() -> ModuleService:
    from data import GradeDocuments, MockOutlines, MockWordBank
    bank = MockWordBank()
    return ModuleService(
        outlines=MockOutlines(bank),
        bank=bank,
        grade_documents=GradeDocuments(),
    )


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

@app.post("/module")
def create_module(
    age: int = Form(...),
    processes: str = Form(...),
):
    """Build a personalized practice module from age + detected processes.

    Parameters
    ----------
    age : int
        Child's age in years.
    processes : str
        JSON array of detected processes, e.g.
        ``[{"process": "Fronting", "position": "Initial",
            "detail": "/k/ -> [t]"}]``
        (the target phoneme is derived from the detail string).

    Returns
    -------
    dict with ``module_id``, ``focus_sounds``, ``focus_processes``,
    ``outline_id``, ``outline_title``, ``levels`` (syllable -> word ->
    phrase -> sentence items), ``rationale``, ``generated_by``.
    """
    try:
        processes_data = json.loads(processes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400,
                            detail=f"processes is not valid JSON: {exc}") from exc

    findings = AssessmentFindings(
        age=age,
        processes=tuple(
            DetectedProcess(
                process=p.get("process", ""),
                position=p.get("position", ""),
                detail=p.get("detail", ""),
            )
            for p in processes_data
        ),
    )

    try:
        module = make_service().build_module(findings)
    except (NoFindingsError, NoOutlineError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "module_id": module.module_id,
        "focus_sounds": [s.sound for s in module.focus_sounds],
        "focus_processes": module.focus_processes,
        "outline_id": module.outline_id,
        "outline_title": module.outline_title,
        "levels": [
            {
                "level": level.value,
                "items": [
                    {"text": item.text, "target_sound": item.target_sound,
                     "position": item.position}
                    for item in items
                ],
            }
            for level, items in module.levels.items()
        ],
        "rationale": module.rationale,
        "generated_by": module.generated_by,
        "warning": module.warning,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "dynamic-modules",
            "provider": config.llm_provider, "model": config.llm_model}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
    )
