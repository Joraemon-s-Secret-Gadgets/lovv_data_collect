from __future__ import annotations

import re
from typing import Final


NON_PAGE_TITLE_PREFIXES: Final[tuple[str, ...]] = (
    "Category:",
    "File:",
    "Help:",
    "Portal:",
    "Template:",
    "Wikipedia:",
)
CJK_TITLE_RE: Final[re.Pattern[str]] = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def is_non_page_title(title: str) -> bool:
    return title.startswith(NON_PAGE_TITLE_PREFIXES)


def is_valid_linked_title(target_lang: str, title: str) -> bool:
    if is_non_page_title(title):
        return False
    if target_lang == "en" and CJK_TITLE_RE.search(title):
        return False
    return True
