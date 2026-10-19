"""Subprocess entry point for PDF/DOCX parsing.

The API process never imports the document parsers on the request path. This
module reads one JSON job from stdin and writes one JSON result to stdout.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        job = json.loads(sys.stdin.read() or "{}")
        kind = job.get("kind")
        path = job.get("path")
        if kind == "pdf":
            from .pdf import parse_pdf

            document = parse_pdf(path)
        elif kind == "docx":
            from .docx import parse_docx

            document = parse_docx(path)
        else:
            raise ValueError("unsupported_kind")
        payload = {"ok": True, **document.as_json()}
    except ValueError as exc:
        payload = {"ok": False, "code": str(exc) or "parse_failed"}
    except Exception:  # noqa: BLE001 - never expose parser internals
        payload = {"ok": False, "code": "parse_failed"}
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
