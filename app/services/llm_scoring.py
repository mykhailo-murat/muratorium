from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Iterable

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings


class LLMScore(BaseModel):
    cluster_id: int
    importance: int = Field(ge=0, le=10)
    urgency: int = Field(ge=0, le=10)
    confidence: float = Field(ge=0.0, le=1.0)
    category: str
    title_uk: str
    summary_uk: str
    short_summary: str
    reason: str


class LLMScoreBatch(BaseModel):
    items: list[LLMScore]


@dataclass(frozen=True)
class ScoreInput:
    cluster_id: int
    title: str
    content: str
    source: str


SYSTEM_PROMPT = (
    "You are a strict JSON scoring engine for urgent news triage. "
    "Return JSON only with root object: {\"items\": [...]} and no markdown. "
    "Always return Ukrainian text for title_uk and summary_uk."
)


def _build_user_prompt(items: Iterable[ScoreInput]) -> str:
    rows = []
    for item in items:
        rows.append(
            {
                "cluster_id": item.cluster_id,
                "source": item.source,
                "title": item.title[:300],
                "content": item.content[:1000],
            }
        )

    return (
        "Score each item and return this JSON schema exactly:\n"
        "{"
        "\"items\":[{"
        "\"cluster_id\":int,"
        "\"importance\":int(0..10),"
        "\"urgency\":int(0..10),"
        "\"confidence\":float(0..1),"
        "\"category\":string,"
        "\"title_uk\":string,"
        "\"summary_uk\":string,"
        "\"short_summary\":string(one line),"
        "\"reason\":string(one line)"
        "}]"
        "}\n\n"
        f"Input items:\n{json.dumps(rows, ensure_ascii=False)}"
    )


def _call_openai(messages: list[dict]) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    payload = {
        "model": settings.openai_model,
        "temperature": 0,
        "messages": messages,
    }

    last_error: Exception | None = None
    with httpx.Client(timeout=45) as client:
        for attempt in range(3):
            try:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code in (429, 500, 502, 503, 504):
                    response.raise_for_status()
                response.raise_for_status()
                data = response.json()
                break
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        else:
            if last_error:
                raise last_error
            raise RuntimeError("OpenAI request failed")

    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenAI returned empty content")
    return content.strip()


def score_batch(items: list[ScoreInput]) -> dict[int, LLMScore]:
    if not items:
        return {}

    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(items)},
    ]

    raw = _call_openai(base_messages)
    try:
        parsed = LLMScoreBatch.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        repair_messages = [
            *base_messages,
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "Your previous response was invalid. "
                    "Return valid JSON only matching the required schema."
                ),
            },
        ]
        repaired = _call_openai(repair_messages)
        parsed = LLMScoreBatch.model_validate(json.loads(repaired))

    return {entry.cluster_id: entry for entry in parsed.items}
