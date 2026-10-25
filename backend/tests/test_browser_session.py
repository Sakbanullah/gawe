from gawe.jobs.browser import session


def test_classify_login_and_block_markers() -> None:
    assert session.classify("https://site.test/jobs", "<html>jobs</html>") == "ok"
    assert session.classify("https://site.test/login", "<html></html>") == "login_required"
    assert session.classify("https://site.test/jobs", "<p>Please verify you are human</p>") == "blocked"
    assert session.classify("https://site.test/jobs", "<html></html>", "Just a moment...") == "blocked"


def test_status_without_profile_is_no_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    status = session.status("https://example.test/jobs")
    assert status.state == "no_profile"
    assert status.url is None


def test_clear_removes_only_the_profile_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from gawe.jobs.browser import profile

    path = profile.profile_dir()
    path.mkdir(parents=True)
    (path / "Cookies").write_text("placeholder", encoding="utf-8")
    assert profile.exists() is True
    assert profile.clear() is True
    assert profile.exists() is False
    assert profile.clear() is False
    assert path.parent.is_dir()
