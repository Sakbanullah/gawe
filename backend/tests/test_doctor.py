from __future__ import annotations

import json

from gawe.cli import main


def test_doctor_reports_environment(repo_root, capsys) -> None:
    code = main(["--config", str(repo_root / "config.toml"), "doctor"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["bind_loopback"] is True
    assert report["schema_version"] == "0011_documents"
    assert report["key_source"] in {"keyring", "env", "missing"}
    assert report["frontend_build"] in {"present", "missing"}
    assert "super-secret" not in json.dumps(report)


def test_doctor_without_config_reports_error(tmp_path, capsys) -> None:
    code = main(["--config", str(tmp_path / "absent.toml"), "doctor"])
    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert report["errors"]
