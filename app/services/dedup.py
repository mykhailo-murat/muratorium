import hashlib
import re


def normalize_text(text: str) -> str:
    # Remove URLs and excessive whitespace
    text = re.sub(r"https?://\S+", "", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_content_hash(title: str, content: str) -> str:
    base = normalize_text(title) + " | " + normalize_text(content)[:600]
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
