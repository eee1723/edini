"""Version session naming: core_path::vN separator scheme.

Pi sees only a session-name string; the ::vN suffix is our convention for
enumerating versions of a single HDA node's modeling attempts. Pi is unaware
of the versioning — it just stores sessions by name.
"""

SEP = "::v"


def make_version_session_name(core_path: str, version: int) -> str:
    """Build a versioned session name: f'{core_path}::v{version}'."""
    return f"{core_path}{SEP}{version}"


def parse_version_session_name(name: str) -> tuple[str, int | None]:
    """Parse a session name into (core_path, version).

    Returns (name, None) if no ::vN suffix is present.
    """
    if SEP in name:
        path, vstr = name.rsplit(SEP, 1)
        try:
            return path, int(vstr)
        except ValueError:
            return name, None
    return name, None


def next_version(existing_versions: list[int | None]) -> int:
    """Compute the next version number from a list of existing versions.

    None entries are ignored. Returns 1 if list is empty/all-None.
    """
    nums = [v for v in existing_versions if v is not None]
    return max(nums) + 1 if nums else 1
