"""LLM clients — implementations of the LLMClient port.

ZenLLMClient talks to OpenCode Zen (OpenAI-compatible chat completions).
The API key is read from the environment (``ZEN_API_KEY``) — never from
config or files.  Tests use httpx MockTransport, so no real calls.
"""

import os
from typing import Optional

from domain.ports import LLMClient


class LLMError(Exception):
    """The LLM provider failed (network, auth, timeout...)."""


class ZenLLMClient(LLMClient):
    """OpenCode Zen chat-completions client (OpenAI-compatible SDK)."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: Optional[str] = None,
        api_key_env: str = "ZEN_API_KEY",
        timeout: float = 30.0,
        http_client=None,
    ):
        from openai import OpenAI

        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise LLMError(
                f"ZEN_API_KEY is not set (expected env var '{api_key_env}')"
            )
        self._model = model
        self._client = OpenAI(
            base_url=base_url,
            api_key=key,
            timeout=timeout,
            http_client=http_client,
        )

    def complete(self, *, system: str, user: str) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.4,
            )
        except Exception as exc:
            raise LLMError(f"OpenCode Zen request failed: {exc}") from exc
        content = resp.choices[0].message.content
        if not content:
            raise LLMError("OpenCode Zen returned an empty response")
        return content
