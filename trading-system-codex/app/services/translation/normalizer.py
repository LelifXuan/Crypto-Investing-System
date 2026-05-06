from __future__ import annotations

import hashlib
import re

_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ENGLISH_PATTERN = re.compile(r"[A-Za-z]{3,}")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def looks_like_english(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    if _CJK_PATTERN.search(text):
        return False
    return bool(_ENGLISH_PATTERN.search(text))


def is_probably_mojibake(text: str | None) -> bool:
    if not text:
        return False
    has_cjk = bool(_CJK_PATTERN.search(text))
    has_non_ascii = any(ord(ch) > 127 for ch in text)
    return has_non_ascii and not has_cjk


def normalize_segment(text: str) -> str:
    collapsed = _WHITESPACE_PATTERN.sub(" ", (text or "").strip())
    return collapsed


def normalized_text_hash(text: str) -> str:
    return hashlib.sha256(normalize_segment(text).encode("utf-8")).hexdigest()
