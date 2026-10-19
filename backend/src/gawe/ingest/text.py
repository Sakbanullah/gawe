"""TXT/MD ingest using the standard library."""

from __future__ import annotations

import re

from .types import Block, DocumentText

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")


def parse_text(data: bytes) -> DocumentText:
    text = data.decode("utf-8-sig")
    blocks: list[Block] = []
    section: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        heading = HEADING_RE.match(raw)
        if heading:
            section = heading.group(1).strip().lower()
        blocks.append(
            Block(
                text=raw.rstrip(),
                locator={
                    "page": None,
                    "section": section,
                    "block_id": f"line:{number}",
                    "char_start": None,
                    "char_end": None,
                },
            )
        )
    return DocumentText(blocks=blocks, page_count=None)
