from __future__ import annotations

import argparse
import re
from pathlib import Path

from sqlalchemy import select

from app.db.models import Source
from app.db.session import SessionLocal

LINE_PATTERN = re.compile(r"^\s*(?P<name>.+?)\s*-\s*\[(?P<url>https?://[^\]]+)\]\s*$")


def parse_sources_file(path: Path) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_PATTERN.match(line)
        if not match:
            continue
        name = match.group("name").strip()
        url = match.group("url").strip()
        items.append((name, url))
    return items


def seed_sources(path: Path, default_trust_score: int = 7) -> tuple[int, int]:
    parsed = parse_sources_file(path)
    if not parsed:
        return 0, 0

    created = 0
    updated = 0

    with SessionLocal() as db:
        for name, url in parsed:
            existing = db.scalar(
                select(Source).where((Source.name == name) | (Source.url == url))
            )
            if existing:
                changed = False
                if existing.name != name:
                    existing.name = name
                    changed = True
                if existing.url != url:
                    existing.url = url
                    changed = True
                if existing.kind != "rss":
                    existing.kind = "rss"
                    changed = True
                if not existing.is_enabled:
                    existing.is_enabled = True
                    changed = True
                if changed:
                    updated += 1
                continue

            db.add(
                Source(
                    kind="rss",
                    name=name,
                    url=url,
                    trust_score=default_trust_score,
                    is_enabled=True,
                )
            )
            created += 1

        db.commit()

    return created, updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed RSS sources from sources.txt")
    parser.add_argument("--file", default="sources.txt", help="Path to sources file")
    parser.add_argument(
        "--trust-score",
        type=int,
        default=7,
        help="Default trust_score for newly created sources",
    )
    args = parser.parse_args()

    created, updated = seed_sources(Path(args.file), default_trust_score=args.trust_score)
    print(f"Seed complete. created={created}, updated={updated}")


if __name__ == "__main__":
    main()
