"""Version name parse/format: core_path::vN."""
from edini.ui.components.version_naming import (
    make_version_session_name, parse_version_session_name, next_version
)


def test_make_version_name():
    assert make_version_session_name("/obj/geo1/build1", 3) == "/obj/geo1/build1::v3"


def test_parse_versioned_name():
    assert parse_version_session_name("/obj/x::v5") == ("/obj/x", 5)


def test_parse_unversioned_returns_none_version():
    assert parse_version_session_name("/obj/x") == ("/obj/x", None)


def test_parse_name_without_separator():
    assert parse_version_session_name("plain_name") == ("plain_name", None)


def test_next_version_from_empty():
    assert next_version([]) == 1


def test_next_version_from_existing():
    assert next_version([1, 2, 4]) == 5


def test_next_version_handles_none():
    assert next_version([1, None, 3]) == 4


def test_next_version_single():
    assert next_version([1]) == 2


def test_roundtrip():
    name = make_version_session_name("/obj/a/b", 7)
    path, ver = parse_version_session_name(name)
    assert path == "/obj/a/b"
    assert ver == 7
