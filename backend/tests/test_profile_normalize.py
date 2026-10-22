"""Validator tolerance for the shapes real models emit.

Every case here was produced by a live model on a real CV and silently lost
candidate data before the validator learned to normalize it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gawe.documents.ai_draft import _restore_missing_facts
from gawe.profile.validate import validate_extraction

SOURCE = (
    "Sakbanullah Dwi Oktavian\n"
    "IT Intern | Balai Pemasyarakatan Kelas II OKU Induk Dec 2025 - Jun 2026\n"
    "Merancang relational database dan mengembangkan backend CRUD dengan Node.js.\n"
    "Oil Palm Fruit Maturity Detection | Undergraduate Thesis | 2025\n"
    "Membandingkan YOLOv8s dan Faster R-CNN untuk object detection.\n"
    "Backend: Node.js, Express.js, NestJS, PostgreSQL, MySQL\n"
)


def _raw(**overrides) -> dict:
    raw = {
        "schema_version": 1,
        "personal": {"full_name": "Sakbanullah Dwi Oktavian"},
        "education": [],
        "experience": [],
        "skills": [],
        "projects": [],
        "certifications": [],
        "languages": [],
        "awards": [],
        "work_authorization": [],
        "work_preferences": {},
        "evidence_index": {
            "ev_1": {"quote": "Merancang relational database", "source": "cv"},
            "ev_2": {"quote": "Membandingkan YOLOv8s dan Faster R-CNN", "source": "cv"},
            "ev_3": {"quote": "Backend: Node.js, Express.js, NestJS", "source": "cv"},
        },
        "conflicts": [],
    }
    raw.update(overrides)
    return raw


def test_items_without_id_are_kept() -> None:
    raw = _raw(skills=[{"name": "Node.js", "evidence": ["ev_3"]}])
    content, _evidence, _conflicts, report = validate_extraction(raw, SOURCE, "doc_1")
    assert [item["name"] for item in content["skills"]] == ["Node.js"]
    assert content["skills"][0]["id"]
    assert not [path for path in report.dropped if path.startswith("skills")]


def test_project_bullets_become_description() -> None:
    raw = _raw(
        projects=[
            {
                "name": "Oil Palm Fruit Maturity Detection",
                "context": "Undergraduate Thesis",
                "year": "2025",
                "bullets": ["Membandingkan YOLOv8s dan Faster R-CNN untuk object detection."],
                "evidence": ["ev_2"],
            }
        ]
    )
    content, _evidence, _conflicts, _report = validate_extraction(raw, SOURCE, "doc_1")
    project = content["projects"][0]
    assert project["role"] == "Undergraduate Thesis"
    assert project["start"] == "2025"
    assert "YOLOv8s" in project["description"]
    # Contract fields only: the model aliases must not reach stored content.
    for alias in ("bullets", "context", "year", "link"):
        assert alias not in project


def test_string_bullet_inherits_parent_evidence() -> None:
    raw = _raw(
        experience=[
            {
                "id": "exp_1",
                "company": "Balai Pemasyarakatan",
                "title": "IT Intern",
                "bullets": ["Merancang relational database"],
                "evidence": ["ev_1"],
            }
        ]
    )
    content, _evidence, _conflicts, _report = validate_extraction(raw, SOURCE, "doc_1")
    bullets = content["experience"][0]["bullets"]
    assert [bullet["text"] for bullet in bullets] == ["Merancang relational database"]
    assert bullets[0]["evidence"] == ["ev_1"]


def test_grouped_skill_line_is_split() -> None:
    raw = _raw(
        skills=[
            {"name": "Backend: Node.js, Express.js, NestJS", "evidence": ["ev_3"]},
            {"name": "MySQL, PostgreSQL, SQL", "evidence": ["ev_3"]},
        ]
    )
    content, _evidence, _conflicts, _report = validate_extraction(raw, SOURCE, "doc_1")
    names = [item["name"] for item in content["skills"]]
    assert names == [
        "Node.js",
        "Express.js",
        "NestJS",
        "MySQL",
        "PostgreSQL",
        "SQL",
    ]
    assert len({item["id"] for item in content["skills"]}) == 6


def test_writer_restores_facts_the_model_omitted() -> None:
    baseline = {
        "projects": [{"id": "prj_2", "name": "Oil Palm Fruit Maturity Detection"}],
        "skills": [{"id": "sk_7", "name": "YOLOv8"}, {"id": "sk_1", "name": "Node.js"}],
        "education": [],
        "certifications": [],
        "languages": [],
    }
    content = {"skills": [{"id": "sk_1", "name": "Node.js"}]}
    _restore_missing_facts(content, baseline)
    assert [item["id"] for item in content["skills"]] == ["sk_1", "sk_7"]
    assert [item["id"] for item in content["projects"]] == ["prj_2"]


def test_writer_does_not_duplicate_a_skill_without_id() -> None:
    baseline = {"skills": [{"id": "sk_1", "name": "Node.js"}], "projects": []}
    content = {"skills": [{"name": "Node.js"}]}
    _restore_missing_facts(content, baseline)
    assert len(content["skills"]) == 1
