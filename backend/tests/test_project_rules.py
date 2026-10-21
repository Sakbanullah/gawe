from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BACKEND_SRC = ROOT / "backend" / "src" / "gawe"

FORBIDDEN_UI = (
    "antd",
    "@chakra-ui",
    "@mui/",
    "bootstrap",
    "tailwindcss",
    "@emotion/",
    "styled-components",
)


def test_single_ui_library() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    offenders = [name for name in dependencies if name.startswith(FORBIDDEN_UI)]
    assert offenders == []
    assert "@mantine/core" in dependencies


def test_dependencies_are_exactly_pinned() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    for name, version in package["dependencies"].items():
        assert version[0].isdigit(), f"{name} is not pinned to an exact version"


def test_css_exceptions_only() -> None:
    css = [path.relative_to(FRONTEND) for path in FRONTEND.glob("src/**/*.css")]
    assert css == [Path("src/styles/exceptions.css")]
    assert "Documented CSS exceptions" in (FRONTEND / "src/styles/exceptions.css").read_text(
        encoding="utf-8"
    )


def test_no_server_side_html_templates() -> None:
    templates = [path for path in BACKEND_SRC.rglob("*") if path.suffix in {".html", ".jinja", ".j2"}]
    assert templates == []
    for path in BACKEND_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "Jinja2Templates" not in text
        assert "TemplateResponse" not in text


def test_no_real_provider_or_model_assumed() -> None:
    config = (ROOT / "config.example.toml").read_text(encoding="utf-8")
    for vendor in ("openai.com", "anthropic", "googleapis", "azure", "deepseek", "mistral"):
        assert vendor not in config.lower()
    assert "provider_a" in config
