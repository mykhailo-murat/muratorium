from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Source
from app.db.session import SessionLocal

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: HttpUrl
    trust_score: int = Field(default=7, ge=1, le=10)
    is_enabled: bool = True


class SourceOut(BaseModel):
    id: int
    kind: str
    name: str
    url: str
    trust_score: int
    is_enabled: bool


@router.get("", response_model=list[SourceOut])
def list_sources() -> list[SourceOut]:
    with SessionLocal() as db:
        rows = db.scalars(select(Source).order_by(Source.id.asc())).all()
        return [
            SourceOut(
                id=row.id,
                kind=row.kind,
                name=row.name,
                url=row.url,
                trust_score=row.trust_score,
                is_enabled=row.is_enabled,
            )
            for row in rows
        ]


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def add_source(payload: SourceCreate) -> SourceOut:
    with SessionLocal() as db:
        existing = db.scalar(
            select(Source).where((Source.name == payload.name) | (Source.url == str(payload.url)))
        )
        if existing:
            raise HTTPException(status_code=409, detail="Source with same name or url already exists")

        row = Source(
            kind="rss",
            name=payload.name.strip(),
            url=str(payload.url),
            trust_score=payload.trust_score,
            is_enabled=payload.is_enabled,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Source already exists")
        db.refresh(row)
        return SourceOut(
            id=row.id,
            kind=row.kind,
            name=row.name,
            url=row.url,
            trust_score=row.trust_score,
            is_enabled=row.is_enabled,
        )


@router.patch("/{source_id}/enable", response_model=SourceOut)
def enable_source(source_id: int) -> SourceOut:
    with SessionLocal() as db:
        row = db.scalar(select(Source).where(Source.id == source_id))
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
        row.is_enabled = True
        db.commit()
        db.refresh(row)
        return SourceOut(
            id=row.id,
            kind=row.kind,
            name=row.name,
            url=row.url,
            trust_score=row.trust_score,
            is_enabled=row.is_enabled,
        )


@router.patch("/{source_id}/disable", response_model=SourceOut)
def disable_source(source_id: int) -> SourceOut:
    with SessionLocal() as db:
        row = db.scalar(select(Source).where(Source.id == source_id))
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
        row.is_enabled = False
        db.commit()
        db.refresh(row)
        return SourceOut(
            id=row.id,
            kind=row.kind,
            name=row.name,
            url=row.url,
            trust_score=row.trust_score,
            is_enabled=row.is_enabled,
        )


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int) -> None:
    with SessionLocal() as db:
        row = db.scalar(select(Source).where(Source.id == source_id))
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
        db.delete(row)
        db.commit()
