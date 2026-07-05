"""Version scanner: list Pi sessions for a given core_path."""
import sys, json, os, time
sys.path.insert(0, "python3.11libs")
from pathlib import Path


def _make_session_file(dir_path: Path, session_name: str, user_msg: str = "hello") -> Path:
    """Helper: create a fake Pi session jsonl file."""
    dir_path.mkdir(parents=True, exist_ok=True)
    fname = f"{int(time.time())}_{session_name.replace('/','_').replace(':','_')}.jsonl"
    fpath = dir_path / fname
    lines = [
        json.dumps({"sessionName": session_name}),
        json.dumps({"role": "user", "content": user_msg}),
        json.dumps({"role": "assistant", "content": "response"}),
    ]
    fpath.write_text("\n".join(lines), encoding="utf-8")
    return fpath


def test_scan_finds_versioned_sessions(tmp_path, monkeypatch):
    from edini.ui import version_scanner
    monkeypatch.setattr(version_scanner, "_pi_sessions_root", lambda: tmp_path)

    cwd_dir = tmp_path / "some-cwd-hash"
    _make_session_file(cwd_dir, "/obj/x::v1", "make a box")
    _make_session_file(cwd_dir, "/obj/x::v2", "spiral stairs")
    _make_session_file(cwd_dir, "/obj/other::v1", "different node")  # different core_path

    versions = version_scanner.scan_node_versions("/obj/x")
    version_nums = sorted(v["version"] for v in versions)
    assert version_nums == [1, 2]


def test_scan_returns_empty_when_no_match(tmp_path, monkeypatch):
    from edini.ui import version_scanner
    monkeypatch.setattr(version_scanner, "_pi_sessions_root", lambda: tmp_path)
    assert version_scanner.scan_node_versions("/obj/none") == []


def test_scan_returns_empty_when_root_missing(tmp_path, monkeypatch):
    from edini.ui import version_scanner
    nonexistent = tmp_path / "does_not_exist"
    monkeypatch.setattr(version_scanner, "_pi_sessions_root", lambda: nonexistent)
    assert version_scanner.scan_node_versions("/obj/x") == []


def test_scan_extracts_summary(tmp_path, monkeypatch):
    from edini.ui import version_scanner
    monkeypatch.setattr(version_scanner, "_pi_sessions_root", lambda: tmp_path)
    cwd_dir = tmp_path / "hash"
    _make_session_file(cwd_dir, "/obj/x::v1", "build a staircase with 12 steps")
    versions = version_scanner.scan_node_versions("/obj/x")
    assert len(versions) == 1
    assert "staircase" in versions[0]["summary"]


def test_scan_excludes_unversioned_sessions(tmp_path, monkeypatch):
    """Sessions without ::vN suffix should be excluded from version list."""
    from edini.ui import version_scanner
    monkeypatch.setattr(version_scanner, "_pi_sessions_root", lambda: tmp_path)
    cwd_dir = tmp_path / "hash"
    _make_session_file(cwd_dir, "/obj/x", "no version suffix")  # no ::vN
    _make_session_file(cwd_dir, "/obj/x::v1", "versioned")
    versions = version_scanner.scan_node_versions("/obj/x")
    assert len(versions) == 1
    assert versions[0]["version"] == 1


def test_scan_sorted_by_version(tmp_path, monkeypatch):
    from edini.ui import version_scanner
    monkeypatch.setattr(version_scanner, "_pi_sessions_root", lambda: tmp_path)
    cwd_dir = tmp_path / "hash"
    _make_session_file(cwd_dir, "/obj/x::v3", "third")
    _make_session_file(cwd_dir, "/obj/x::v1", "first")
    _make_session_file(cwd_dir, "/obj/x::v2", "second")
    versions = version_scanner.scan_node_versions("/obj/x")
    version_nums = [v["version"] for v in versions]
    assert version_nums == [1, 2, 3]


def test_scan_includes_session_file_path(tmp_path, monkeypatch):
    from edini.ui import version_scanner
    monkeypatch.setattr(version_scanner, "_pi_sessions_root", lambda: tmp_path)
    cwd_dir = tmp_path / "hash"
    _make_session_file(cwd_dir, "/obj/x::v1", "test")
    versions = version_scanner.scan_node_versions("/obj/x")
    assert "session_file" in versions[0]
    assert os.path.exists(versions[0]["session_file"])
