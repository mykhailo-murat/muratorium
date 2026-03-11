from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Iterable

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMScore(BaseModel):
    cluster_id: int
    importance: int = Field(ge=0, le=10)
    urgency: int = Field(ge=0, le=10)
    confidence: float = Field(ge=0.0, le=1.0)
    category: str = Field(min_length=1)
    title_uk: str = Field(min_length=1)
    summary_uk: str = Field(min_length=1)
    short_summary: str = Field(min_length=1)
    reason: str = Field(min_length=1)


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
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")


def _is_ukrainian_text(text: str) -> bool:
    return bool(text and _CYRILLIC_RE.search(text))


def _find_language_violations(parsed: LLMScoreBatch) -> list[int]:
    bad_cluster_ids: list[int] = []
    for item in parsed.items:
        if not _is_ukrainian_text(item.title_uk) or not _is_ukrainian_text(item.summary_uk):
            bad_cluster_ids.append(item.cluster_id)
    return bad_cluster_ids


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
        "Urgency rubric:\n"
        "- urgency=10 only for extreme events with immediate large-scale impact (e.g. assassination of top leader, confirmed major conflict escalation, new dangerous epidemic strain).\n"
        "- urgency=8..9 for major escalations with immediate risk.\n"
        "- urgency=6..7 for important but not extreme developments.\n"
        "- urgency=3..5 for routine high-interest updates.\n"
        "- urgency=0..2 for background/noise.\n"
        "Do not assign urgency=10 to weather damage reports or policy recommendations (for example: tornado damage, strategic oil reserve recommendation).\n\n"
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
    logger.info(
        "OpenAI request prepared: model=%s messages=%s",
        settings.openai_model,
        len(messages),
    )

    last_error: Exception | None = None
    with httpx.Client(timeout=45) as client:
        for attempt in range(3):
            try:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code in (429, 500, 502, 503, 504):
                    response.raise_for_status()
                response.raise_for_status()
                data = response.json()
                logger.info(
                    "OpenAI request succeeded: status=%s attempt=%s",
                    response.status_code,
                    attempt + 1,
                )
                break
            except httpx.HTTPStatusError as exc:
                last_error = exc
                logger.warning(
                    "OpenAI request failed: status=%s attempt=%s",
                    exc.response.status_code,
                    attempt + 1,
                )
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
    logger.info("OpenAI response received: chars=%s", len(content.strip()))
    return content.strip()


def score_batch(items: list[ScoreInput]) -> dict[int, LLMScore]:
    if not items:
        return {}
    logger.info(
        "Urgent scoring batch started: items=%s cluster_ids=%s",
        len(items),
        [item.cluster_id for item in items],
    )

    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(items)},
    ]

    raw = _call_openai(base_messages)
    try:
        parsed = LLMScoreBatch.model_validate(json.loads(raw))
        invalid_ua_ids = _find_language_violations(parsed)
        logger.info("Urgent scoring parsed successfully: parsed_items=%s", len(parsed.items))
    except (json.JSONDecodeError, ValidationError):
        parsed = None
        invalid_ua_ids = []
        logger.warning("Urgent scoring parse failed; repair attempt will be used")

    if parsed is None or invalid_ua_ids:
        if invalid_ua_ids:
            logger.warning("Urgent scoring language violations for clusters=%s", invalid_ua_ids)
        repair_messages = [
            *base_messages,
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "Your previous response was invalid. "
                    "Return valid JSON only matching the required schema. "
                    "Also ensure title_uk and summary_uk are non-empty and in Ukrainian."
                ),
            },
        ]
        repaired = _call_openai(repair_messages)
        parsed = LLMScoreBatch.model_validate(json.loads(repaired))
        invalid_ua_ids = _find_language_violations(parsed)
        logger.info("Urgent scoring repair parsed successfully: parsed_items=%s", len(parsed.items))
        if invalid_ua_ids:
            invalid_set = set(invalid_ua_ids)
            parsed = LLMScoreBatch(
                items=[entry for entry in parsed.items if entry.cluster_id not in invalid_set]
            )
            logger.warning("Urgent scoring dropped non-Ukrainian items: clusters=%s", invalid_ua_ids)

    logger.info("Urgent scoring completed: accepted_items=%s", len(parsed.items))
    return {entry.cluster_id: entry for entry in parsed.items}
