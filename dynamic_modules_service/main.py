"""Dynamic Modules Service — FastAPI app (port 8002).

Builds personalized practice modules (syllables -> words -> phrases ->
sentences) from phoneme assessment findings, using OpenCode Zen's
DeepSeek V4 Flash Free for humanlike decisions (rule-based fallback
when the LLM is unavailable).
"""

import os
import sys
import logging
import uvicorn

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config import config

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(title="Dynamic Modules Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "dynamic-modules",
            "provider": config.llm_provider, "model": config.llm_model}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.port)
