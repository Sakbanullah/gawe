"""PDF text extraction with page/block locators (PyMuPDF)."""

from __future__ import annotations

from .types import Block, DocumentText


def parse_pdf(path: str) -> DocumentText:
    import pymupdf

    blocks: list[Block] = []
    with pymupdf.open(path) as document:
        if document.needs_pass:
            raise ValueError("pdf_encrypted")
        for page_index in range(document.page_count):
            page = document[page_index]
            for block_index, block in enumerate(page.get_text("blocks")):
                text = str(block[4]).strip()
                if not text:
                    continue
                blocks.append(
                    Block(
                        text=text,
                        locator={
                            "page": page_index + 1,
                            "section": None,
                            "block_id": f"p{page_index + 1}:b{block_index}",
                            "char_start": None,
                            "char_end": None,
                        },
                    )
                )
        page_count = document.page_count
    if len(" ".join(block.text for block in blocks).strip()) < 40:
        raise ValueError("pdf_no_text")
    return DocumentText(blocks=blocks, page_count=page_count)
