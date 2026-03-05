from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PublishedMessage


def was_published(session: Session, *, channel: str, message_key: str) -> bool:
    existing = session.scalar(
        select(PublishedMessage.id).where(
            PublishedMessage.channel == channel,
            PublishedMessage.message_key == message_key,
        )
    )
    return bool(existing)


def mark_published(
    session: Session,
    *,
    channel: str,
    message_key: str,
    mode: str,
    payload_ref: str | None = None,
) -> None:
    if was_published(session, channel=channel, message_key=message_key):
        return
    session.add(
        PublishedMessage(
            channel=channel,
            message_key=message_key,
            mode=mode,
            payload_ref=payload_ref,
        )
    )
