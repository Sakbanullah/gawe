"""LaTeX rendering, Tectonic compile, and PDF QA (DOCUMENT-GENERATION.md §8).

Rendering is deterministic: the same content dict always produces the same
`.tex` source. The PDF is produced by Tectonic; nothing here calls a model.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TECTONIC_TIMEOUT_S = 120
COMPILE_ATTEMPTS = 2
PAGE_LIMITS = {"cv": 2, "cover_letter": 1}
_ENV_TECTONIC = "GAWE_TECTONIC"


class RenderError(Exception):
    """Compile or QA failed. `code` is safe to show and to store."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def find_tectonic(explicit: str | None = None) -> str | None:
    """Resolve the Tectonic binary: config, environment, PATH, then local install."""
    for candidate in (explicit, os.environ.get(_ENV_TECTONIC)):
        if candidate and Path(candidate).is_file():
            return candidate
    found = shutil.which("tectonic")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Gawe" / "tectonic" / "tectonic.exe"
    return str(local) if local.is_file() else None


# -- LaTeX source ------------------------------------------------------------

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_escape(value: str | None) -> str:
    return "".join(_ESCAPES.get(char, char) for char in (value or ""))


def _date_range(start: str | None, end: str | None) -> str:
    if start and end:
        # A one-year project carries the same value in both fields; printing
        # "2025 -- 2025" reads like a typo to a recruiter.
        return start if start == end else f"{start} -- {end}"
    if start:
        # `end: null` means "unknown", not "current". The profile has no
        # `current` flag, so printing "present" would invent a fact.
        return start
    return end or ""


def _link(url: str) -> str:
    safe = url.replace("\\", "").replace("{", "").replace("}", "")
    return rf"\href{{{safe}}}{{{tex_escape(url)}}}"


_PREAMBLE = r"""\documentclass[10.5pt,letterpaper]{article}
\usepackage[margin=0.6in]{geometry}
\usepackage{fontspec}
\setmainfont{texgyretermes}[
  Extension=.otf,
  UprightFont=*-regular,
  BoldFont=*-bold,
  ItalicFont=*-italic,
  BoldItalicFont=*-bolditalic,
  Ligatures=NoCommon]
\setsansfont{texgyreheros}[
  Extension=.otf,
  UprightFont=*-regular,
  BoldFont=*-bold,
  ItalicFont=*-italic,
  BoldItalicFont=*-bolditalic,
  Ligatures=NoCommon]
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\hypersetup{colorlinks=true,linkcolor=black,urlcolor=blue,pdftitle={%(title)s},pdfauthor={%(author)s}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{2pt}
\pagestyle{empty}
\begin{document}
"""


def _header_lines(header: dict) -> list[str]:
    contact = [
        part
        for part in (
            tex_escape(header.get("email")),
            tex_escape(header.get("phone")),
            tex_escape(header.get("location")),
        )
        if part
    ]
    lines = [rf"{{\LARGE\bfseries {tex_escape(header.get('full_name'))}}}\\[2pt]"]
    if contact:
        lines.append(" $\\cdot$ ".join(contact) + r"\\[2pt]")
    links = [_link(url) for url in header.get("links") or [] if url]
    if links:
        lines.append(" $\\cdot$ ".join(links) + r"\\[2pt]")
    return lines


def _section(title: str) -> list[str]:
    return [rf"\vspace{{4pt}}\section*{{{tex_escape(title)}}}", r"\hrule\vspace{2pt}"]


def build_cv(content: dict, language: str = "en") -> str:
    labels = _LABELS.get(language, _LABELS["en"])
    title = f"CV - {content.get('header', {}).get('full_name') or ''}".strip(" -")
    author = content.get("header", {}).get("full_name") or ""
    body: list[str] = list(_header_lines(content.get("header") or {}))

    summary = content.get("summary") or {}
    if summary.get("text"):
        body += _section(labels["summary"])
        body.append(tex_escape(summary["text"]) + r"\par")

    skills = [skill for skill in content.get("skills") or [] if skill.get("name")]
    if skills:
        body += _section(labels["skills"])
        body.append(
            ", ".join(tex_escape(skill["name"]) for skill in skills) + r"\par"
        )

    experience = content.get("experience") or []
    if experience:
        body += _section(labels["experience"])
        for role in experience:
            heading = " -- ".join(
                part for part in (tex_escape(role.get("title")), tex_escape(role.get("company"))) if part
            )
            meta = " | ".join(
                part
                for part in (
                    tex_escape(role.get("location")),
                    _date_range(role.get("start"), role.get("end")),
                )
                if part
            )
            body.append(rf"\textbf{{{heading}}}")
            if meta:
                body.append(r" \hfill " + meta)
            body.append(r"\par")
            bullets = [item for item in role.get("bullets") or [] if item.get("text")]
            if bullets:
                body.append(r"\begin{itemize}[leftmargin=1.2em,itemsep=1pt,topsep=2pt]")
                body += [rf"\item {tex_escape(item['text'])}" for item in bullets]
                body.append(r"\end{itemize}")

    projects = content.get("projects") or []
    if projects:
        body += _section(labels["projects"])
        for project in projects:
            heading = tex_escape(project.get("name"))
            if project.get("role"):
                heading += f" -- {tex_escape(project['role'])}"
            body.append(rf"\textbf{{{heading}}}")
            dates = _date_range(project.get("start"), project.get("end"))
            if dates:
                body.append(r" \hfill " + dates)
            body.append(r"\par")
            if project.get("description"):
                body.append(tex_escape(project["description"]) + r"\par")

    education = content.get("education") or []
    if education:
        body += _section(labels["education"])
        for item in education:
            heading = " -- ".join(
                part
                for part in (tex_escape(item.get("degree")), tex_escape(item.get("institution")))
                if part
            )
            dates = _date_range(item.get("start"), item.get("end"))
            body.append(rf"\textbf{{{heading}}}")
            if dates:
                body.append(r" \hfill " + dates)
            body.append(r"\par")

    certifications = content.get("certifications") or []
    if certifications:
        body += _section(labels["certifications"])
        for item in certifications:
            line = tex_escape(item.get("name"))
            if item.get("issuer"):
                line += f", {tex_escape(item['issuer'])}"
            if item.get("date"):
                line += f" ({tex_escape(item['date'])})"
            body.append(rf"\item {line}")
        body.insert(len(body) - len(certifications), r"\begin{itemize}[leftmargin=1.2em,itemsep=1pt]")
        body.append(r"\end{itemize}")

    languages = content.get("languages") or []
    if languages:
        body += _section(labels["languages"])
        body.append(
            ", ".join(
                " -- ".join(
                    part
                    for part in (tex_escape(item.get("name")), tex_escape(item.get("level")))
                    if part
                )
                for item in languages
            )
            + r"\par"
        )

    preamble = _PREAMBLE % {"title": tex_escape(title), "author": tex_escape(author)}
    return preamble + "\n".join(body) + "\n\\end{document}\n"


def build_cover_letter(content: dict, language: str = "en") -> str:
    labels = _LABELS.get(language, _LABELS["en"])
    header = content.get("header") or {}
    author = header.get("full_name") or ""
    title = f"Cover Letter - {author}".strip(" -")
    body: list[str] = list(_header_lines(header))

    target = content.get("target") or {}
    if target.get("company") or target.get("title"):
        body.append(
            tex_escape(
                " | ".join(
                    part for part in (target.get("title"), target.get("company")) if part
                )
            )
            + r"\par\vspace{6pt}"
        )
    if content.get("greeting"):
        body.append(tex_escape(content["greeting"]) + r"\par\vspace{4pt}")

    for paragraph in content.get("paragraphs") or []:
        if paragraph.get("text"):
            body.append(tex_escape(paragraph["text"]) + r"\par\vspace{4pt}")

    if content.get("closing"):
        body.append(r"\vspace{4pt}" + tex_escape(content["closing"]) + r"\par")
    if author:
        body.append(r"\vspace{8pt}" + tex_escape(author) + r"\par")

    preamble = _PREAMBLE % {"title": tex_escape(title), "author": tex_escape(author)}
    return preamble + "\n".join(body) + "\n\\end{document}\n"


_LABELS = {
    "en": {
        "summary": "Summary",
        "skills": "Skills",
        "experience": "Experience",
        "projects": "Projects",
        "education": "Education",
        "certifications": "Certifications",
        "languages": "Languages",
    },
    "id": {
        "summary": "Ringkasan",
        "skills": "Keahlian",
        "experience": "Pengalaman",
        "projects": "Proyek",
        "education": "Pendidikan",
        "certifications": "Sertifikasi",
        "languages": "Bahasa",
    },
}


def build(content: dict) -> str:
    kind = content.get("kind")
    language = content.get("language") or "en"
    if kind == "cover_letter":
        return build_cover_letter(content, language)
    return build_cv(content, language)


# -- compile and QA ----------------------------------------------------------


def compile_pdf(tex_source: str, *, tectonic: str | None = None) -> tuple[bytes, str]:
    """Compile LaTeX to PDF. Returns `(pdf_bytes, log)`; raises RenderError."""
    binary = find_tectonic(tectonic)
    if binary is None:
        raise RenderError(
            "tectonic_unavailable",
            "Tectonic tidak ditemukan. Instal Tectonic atau set GAWE_TECTONIC.",
        )
    with tempfile.TemporaryDirectory(prefix="gawe-tex-") as work:
        workdir = Path(work)
        tex_path = workdir / "document.tex"
        tex_path.write_text(tex_source, encoding="utf-8")
        outdir = workdir / "out"
        outdir.mkdir()
        log = ""
        for _ in range(COMPILE_ATTEMPTS):
            try:
                completed = subprocess.run(
                    [binary, "-X", "compile", str(tex_path), "--outdir", str(outdir)],
                    capture_output=True,
                    timeout=TECTONIC_TIMEOUT_S,
                    cwd=workdir,
                )
            except subprocess.TimeoutExpired as exc:
                raise RenderError(
                    "compile_timeout", "Compile Tectonic melebihi 120 detik."
                ) from exc
            log = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
            pdf_path = outdir / "document.pdf"
            if completed.returncode == 0 and pdf_path.is_file():
                return pdf_path.read_bytes(), log
        raise RenderError("compile_failed", "Compile Tectonic gagal.")


def qa(pdf_bytes: bytes, kind: str) -> dict:
    """Deterministic PDF QA: readable text, page limit, links, metadata."""
    import pymupdf

    problems: list[dict] = []
    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - a corrupt PDF must not crash the task
        raise RenderError("pdf_unreadable", "PDF hasil compile tidak dapat dibaca.") from exc
    try:
        page_count = document.page_count
        text = "\n".join(page.get_text() for page in document)
        links = sum(len(page.get_links()) for page in document)
        metadata = document.metadata or {}
    finally:
        document.close()

    limit = PAGE_LIMITS.get(kind, 2)
    if page_count == 0:
        problems.append(_problem("pdf_empty", "PDF tidak memiliki halaman."))
    if page_count > limit:
        problems.append(
            _problem(
                "page_limit_exceeded",
                f"{kind} {page_count} halaman; batas {limit}.",
            )
        )
    if len(text.strip()) < 80:
        problems.append(
            _problem("text_not_extractable", "Teks PDF tidak dapat diekstrak (ATS).")
        )
    if "|" in text and text.count("|") > 6:
        problems.append(_problem("layout_table", "Terdeteksi tabel layout pada PDF."))
    if not (metadata.get("title") or "").strip():
        problems.append(_problem("missing_pdf_title", "Metadata pdftitle kosong."))

    return {
        "ok": not problems,
        "page_count": page_count,
        "page_limit": limit,
        "text_chars": len(text.strip()),
        "links": links,
        "title": metadata.get("title"),
        "author": metadata.get("author"),
        "problems": problems,
    }


def _problem(code: str, message: str) -> dict:
    return {"code": code, "message": message}
