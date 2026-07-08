"""Tests for the hython-visibility / require-hython gate in tests/conftest.py.

The gate exists so a skipped decisive layer can't hide behind a passing mock
count: ``pytest_report_header`` states hython availability loudly, and
``--edini-require-hython`` (or ``EDINI_REQUIRE_HYTHON=1``) turns absence into a
hard failure. These exercise the REAL conftest functions with monkeypatched
HYTHON + a stub config — no subprocess needed, since the only thing worth
asserting is our own decision logic (pytest's handling of Exit raised from
pytest_configure is upstream behavior, not ours).
"""
import pytest


class _FakeConfig:
    """Minimal config stub: getoption() returns whatever the test wants."""

    def __init__(self, require_flag=False):
        self._require_flag = require_flag

    def getoption(self, name, default=None):
        if name == "--edini-require-hython":
            return self._require_flag
        return default


def test_report_header_says_available_when_hython_present(monkeypatch):
    import conftest
    monkeypatch.setattr(conftest, "HYTHON", r"C:\fake\hython.exe")
    header = conftest.pytest_report_header(None)
    text = " ".join(header) if isinstance(header, (list, tuple)) else str(header)
    assert "AVAILABLE" in text and "WILL run" in text


def test_report_header_says_skipped_and_names_modules_when_hython_missing(monkeypatch):
    import conftest
    monkeypatch.setattr(conftest, "HYTHON", None)
    header = conftest.pytest_report_header(None)
    text = " ".join(header) if isinstance(header, (list, tuple)) else str(header)
    assert "NOT FOUND" in text and "SKIP" in text
    # Must name the decisive modules so a silent skip is impossible to miss.
    assert "test_project_hython" in text and "test_skill_workflow_hython" in text
    # Must point at the escape hatch.
    assert "--edini-require-hython" in text


def test_configure_exits_when_required_but_hython_missing(monkeypatch):
    """--edini-require-hython + no hython → must fail loud (not skip)."""
    import conftest
    monkeypatch.setattr(conftest, "HYTHON", None)
    with pytest.raises(BaseException) as exc:
        conftest.pytest_configure(_FakeConfig(require_flag=True))
    assert "hython" in str(exc.value).lower()


def test_configure_env_var_also_triggers_exit(monkeypatch):
    """EDINI_REQUIRE_HYTHON=1 must trigger the gate even without the CLI flag."""
    import conftest
    monkeypatch.setattr(conftest, "HYTHON", None)
    monkeypatch.setenv("EDINI_REQUIRE_HYTHON", "1")
    with pytest.raises(BaseException):
        conftest.pytest_configure(_FakeConfig(require_flag=False))


def test_configure_noop_when_hython_available(monkeypatch):
    """With hython present, --edini-require-hython must NOT exit."""
    import conftest
    monkeypatch.setattr(conftest, "HYTHON", r"C:\fake\hython.exe")
    # Must not raise.
    conftest.pytest_configure(_FakeConfig(require_flag=True))


def test_configure_noop_when_not_required(monkeypatch):
    """No flag + no env, even with hython missing → must NOT exit (skip is fine)."""
    import conftest
    monkeypatch.setattr(conftest, "HYTHON", None)
    monkeypatch.delenv("EDINI_REQUIRE_HYTHON", raising=False)
    conftest.pytest_configure(_FakeConfig(require_flag=False))
