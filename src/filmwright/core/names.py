"""File names made from titles, product names, prefixes and slugs.

    from filmwright.core.names import file_safe
    file_safe("Acme/Tasks: Tour?")   # "acme-tasks-tour"
    file_safe("タスク管理のご紹介")     # "タスク管理のご紹介"

Letters, digits and accent marks of any script are kept, so non-Latin names stay readable. Everything else
(spaces, punctuation, path separators, glob characters, control characters) becomes one dash. The text is
normalised to NFC first, so a title typed with "é" and one pasted as "e" plus a combining accent give the same
name. The result is "" when nothing usable is left; callers pick their own fallback.
"""

from __future__ import annotations

import re
import unicodedata


def file_safe(name: object, *, lower: bool = True, limit: int = 60) -> str:
    text = unicodedata.normalize("NFC", str(name or ""))
    if lower:
        text = text.lower()
    kept = "".join(ch if unicodedata.category(ch)[0] in "LNM" else "-" for ch in text)
    return re.sub(r"-+", "-", kept).strip("-")[:limit].strip("-")


def checked_slug(slug: object, where: str = "slug") -> str:
    """A slug that is used as given in folder and file names: it must already be file-safe, so a typo can't
    write outside the project. Raises ValueError with a suggested slug otherwise."""
    text = str(slug or "")
    good = file_safe(text, lower=False, limit=80)
    if not text or good != text:
        raise ValueError(f"{where}: {text!r} can't be used in a file name; try {good or 'episode-1'!r} "
                         "(letters, digits and dashes)")
    return text
