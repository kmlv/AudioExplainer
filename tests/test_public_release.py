from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("prepare_public_release", ROOT / "scripts/prepare_public_release.py")
assert SPEC and SPEC.loader
PUBLIC_RELEASE = module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLIC_RELEASE)


def test_public_source_set_passes_audit():
    assert PUBLIC_RELEASE.audit_public_files(ROOT) == []


def test_manifest_tracks_all_package_tests_and_templates():
    listed = set(PUBLIC_RELEASE.PUBLIC_FILES)
    expected_groups = {
        path.relative_to(ROOT).as_posix()
        for pattern in (
            "src/audioexplainer/*.py",
            "tests/test_*.py",
            "scripts/*.py",
            "share/templates/discovery/**/*",
        )
        for path in ROOT.glob(pattern)
        if path.is_file()
    }
    listed_groups = {
        name
        for name in listed
        if name.startswith(
            ("src/audioexplainer/", "tests/", "scripts/", "share/templates/discovery/")
        )
    }

    assert listed_groups == expected_groups


def test_export_is_allowlisted_and_reaudited(tmp_path):
    destination = tmp_path / "AudioExplainer"
    count = PUBLIC_RELEASE.export_public_tree(ROOT, destination)

    assert count > 0
    assert (destination / "LICENSE").is_file()
    assert (destination / ".github/workflows/ci.yml").is_file()
    assert not (destination / "deliverables").exists()
    assert PUBLIC_RELEASE.audit_public_files(destination) == []


def test_unlisted_file_is_not_exported(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for relative in PUBLIC_RELEASE.PUBLIC_FILES:
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("safe", encoding="utf-8")
    private_note = source / "docs/private-roadmap.md"
    private_note.parent.mkdir(parents=True, exist_ok=True)
    private_note.write_text("private plans", encoding="utf-8")

    destination = tmp_path / "export"
    PUBLIC_RELEASE.export_public_tree(source, destination)

    assert not (destination / "docs/private-roadmap.md").exists()


def test_export_refuses_to_overwrite(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()

    try:
        PUBLIC_RELEASE.export_public_tree(ROOT, destination)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("export should refuse an existing destination")


def test_audit_rejects_missing_relative_markdown_link(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("See [private notes](docs/private.md).", encoding="utf-8")

    issues = PUBLIC_RELEASE._markdown_link_issues(tmp_path, [readme])

    assert any("Markdown link target is not exported" in issue for issue in issues)


def test_audit_rejects_unallowlisted_binary(tmp_path):
    binary = tmp_path / "deploy.pem"
    binary.write_bytes(b"\xff\xfe\x00secret")

    issues = PUBLIC_RELEASE._text_issues(binary, "scripts/deploy.pem")

    assert any("binary or non-UTF-8" in issue for issue in issues)


def test_audit_rejects_local_identity_and_email(tmp_path):
    note = tmp_path / "note.md"
    sensitive_fixture = (
        "/" + "home/" + "klopez" + "va/project contact " + "me" + "@" + "example.com"
    )
    note.write_text(sensitive_fixture, encoding="utf-8")

    issues = PUBLIC_RELEASE._text_issues(note, "docs/note.md")

    assert any("absolute Linux user path" in issue for issue in issues)
    assert any("email address" in issue for issue in issues)


def test_collection_rejects_top_level_symlink(tmp_path):
    target = tmp_path / "real-readme.md"
    target.write_text("safe", encoding="utf-8")
    (tmp_path / "README.md").symlink_to(target)

    try:
        PUBLIC_RELEASE.collect_public_files(tmp_path)
    except ValueError as exc:
        assert "symlinks are not allowed" in str(exc)
    else:
        raise AssertionError("top-level symlinks should be rejected")
