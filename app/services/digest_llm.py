from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.services.llm_scoring import _call_openai


class DigestItem(BaseModel):
    news_item_id: int
    score: int = Field(ge=0, le=100)
    title_uk: str
    summary_uk: str
    reason_uk: str
    category: str


class DigestResponse(BaseModel):
    items: list[DigestItem]


@dataclass(frozen=True)
class DigestCandidate:
    news_item_id: int
    source: str
    title: str
    content: str
    url: str | None


SYSTEM_PROMPT = (
    "Ти редактор новинного дайджесту для української аудиторії. "
    "Поверни тільки релевантні ТОП-новини для публікації: "
    "1) напряму пов'язані з Україною, або "
    "2) глобальні події з масштабним впливом на багато країн/світ. "
    "Відкидай локальні новини вузького регіону без глобального впливу "
    "(наприклад локальні кримінальні події штату/міста, вузькоспортивні історії). "
    "Поверни тільки JSON без markdown."
)


def _build_user_prompt(candidates: list[DigestCandidate], top_n: int, min_score: int) -> str:
    payload = [
        {
            "news_item_id": item.news_item_id,
            "source": item.source,
            "title": item.title[:400],
            "content": item.content[:1200],
            "url": item.url,
        }
        for item in candidates
    ]
    return (
        "Проаналізуй список і поверни ЛИШЕ найкращі новини для публікації.\n"
        "Вимоги:\n"
        "- обов'язково українська мова для title_uk, summary_uk, reason_uk\n"
        "- score від 0 до 100\n"
        f"- у фінальний список включай тільки score >= {min_score}\n"
        f"- поверни не більше {top_n} записів\n"
        "- якщо релевантних немає, поверни порожній масив\n\n"
        "Схема відповіді:\n"
        "{"
        "\"items\":[{"
        "\"news_item_id\":int,"
        "\"score\":int(0..100),"
        "\"title_uk\":string,"
        "\"summary_uk\":string,"
        "\"reason_uk\":string,"
        "\"category\":string"
        "}]"
        "}\n\n"
        f"Кандидати:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def select_digest_items(
    candidates: list[DigestCandidate],
    *,
    top_n: int,
    min_score: int,
) -> list[DigestItem]:
    if not candidates:
        return []

    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(candidates, top_n=top_n, min_score=min_score)},
    ]

    raw = _call_openai(base_messages)
    try:
        parsed = DigestResponse.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        repair_messages = [
            *base_messages,
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "Невалідний JSON. Поверни тільки валідний JSON за заданою схемою.",
            },
        ]
        repaired = _call_openai(repair_messages)
        parsed = DigestResponse.model_validate(json.loads(repaired))

    filtered = [item for item in parsed.items if item.score >= min_score]
    filtered.sort(key=lambda x: x.score, reverse=True)
    return filtered[:top_n]
