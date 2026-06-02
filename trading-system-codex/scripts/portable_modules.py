"""Parse requirements-portable.txt into importable module names.

The portable preflight and the strict verifier both need to know
which Python packages must be present in the embedded runtime. The
text file is the source of truth: the file lists what is actually
``pip install``-ed, and we derive the importable name list from it.

Format we support:

- ``fastapi==0.115.14`` -> ``fastapi``
- ``uvicorn[standard]==0.34.3`` -> ``uvicorn`` (extras dropped)
- ``package ; sys_platform == 'win32'`` -> ``package``
- ``-r other.txt`` -> recursively resolved when ``include_transitive`` is True
- ``# comment`` and blank lines are ignored
- ``https://...`` direct URLs are ignored (no importable name)

The returned list is deterministic (sorted, deduplicated) so that
callers can use it in equality checks and audit reports.
"""

from __future__ import annotations

import re
from pathlib import Path

# ``pip`` accepts: name, name==X, name>=X, name<=X, name~=X, name!=X,
# name===X, name[extra1,extra2], trailing markers like ``; python_version < '3.10'``,
# and editable / direct URL / path-based requirements.
_NAME_PATTERN = re.compile(
    r"""
    ^\s*
    (?:
        (?P<url>(?:https?://|file:).*?)        # URL requirement - skip
        |
        -r\s+(?P<ref>\S+)                       # -r reference - skip
        |
        -e\s+.*                                 # editable install - skip
        |
        (?P<name>[A-Za-z_][A-Za-z0-9_.\-]*)    # actual package name
    )
    """,
    re.VERBOSE,
)


def _normalise_name(raw: str) -> str | None:
    """Return the importable Python name for a requirement.

    ``PyYAML`` -> ``yaml`` (the actual import), ``typing-extensions`` ->
    ``typing_extensions`` (hyphen to underscore), everything else is
    lowercased as-is.
    """

    if not raw:
        return None
    name = raw.strip()
    # Drop extras like ``uvicorn[standard]``.
    bracket = name.find("[")
    if bracket >= 0:
        name = name[:bracket]
    # Drop version specifiers and environment markers.
    for sep in ("==", ">=", "<=", "~=", "!=", "==="):
        if sep in name:
            name = name.split(sep, 1)[0]
    if ";" in name:
        name = name.split(";", 1)[0]
    name = name.strip()
    if not name:
        return None
    # Project-local import name mapping. Most names map to the
    # lowercased, hyphen-to-underscore form, but a few packages
    # import under a different name than the distribution name.
    canonical = {
        "pyyaml": "yaml",
        "python-dotenv": "dotenv",
        "python-multipart": "multipart",
        "pillow": "PIL",
        "scikit-learn": "sklearn",
    }.get(name.lower().replace("_", "-"))
    if canonical is not None:
        return canonical
    return name.lower().replace("-", "_")


def parse_requirements(
    path: Path,
    *,
    include_transitive: bool = False,
) -> list[str]:
    """Return the deduplicated, sorted list of importable module names.

    When ``include_transitive`` is True, ``-r other.txt`` references
    are followed recursively (relative to ``path.parent``). The
    default is False because the portable bundle only ships the
    top-level requirements.
    """

    seen: set[str] = set()
    ordered: list[str] = []
    for line in _iter_requirements(path, include_transitive=include_transitive):
        match = _NAME_PATTERN.match(line)
        if not match:
            continue
        raw_name = match.group("name")
        if raw_name is None:
            continue
        normalised = _normalise_name(raw_name)
        if normalised is None or normalised in seen:
            continue
        seen.add(normalised)
        ordered.append(normalised)
    return sorted(ordered)


def _iter_requirements(path: Path, *, include_transitive: bool) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"requirements file not found: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r") and include_transitive:
            ref = line[2:].strip()
            ref_path = (path.parent / ref).resolve()
            if ref_path.exists():
                yield from _iter_requirements(ref_path, include_transitive=True)
            continue
        yield raw
