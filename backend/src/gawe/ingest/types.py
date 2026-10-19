"""Document text blocks with stable locators."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Block:
    text: str
    locator: dict

    @property
    def block_id(self) -> str:
        return str(self.locator.get("block_id") or "")


@dataclass
class DocumentText:
    blocks: list[Block] = field(default_factory=list)
    page_count: int | None = None

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    def as_json(self) -> dict:
        return {
            "blocks": [{"text": block.text, "locator": block.locator} for block in self.blocks],
            "page_count": self.page_count,
        }

    @classmethod
    def from_json(cls, payload: dict) -> "DocumentText":
        return cls(
            blocks=[Block(text=item["text"], locator=item["locator"]) for item in payload["blocks"]],
            page_count=payload.get("page_count"),
        )


def normalize_text(value: str) -> str:
    """NFKC, non-breaking spaces, and whitespace collapse. Punctuation is kept."""
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def quote_matches(quote: str, source_text: str) -> bool:
    needle = normalize_text(quote)
    return bool(needle) and needle in normalize_text(source_text)
