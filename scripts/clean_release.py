from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from release_common import PROJECT_ROOT, release_residue  # noqa: E402


def main() -> int:
    findings = release_residue(PROJECT_ROOT)
    if findings:
        print("removing release residue:")
        for path in findings[:200]:
            print(f"- {path.relative_to(PROJECT_ROOT).as_posix()}")
        if len(findings) > 200:
            print(f"... and {len(findings) - 200} more")

        directories = sorted(
            {path.parent for path in findings if path.parent != PROJECT_ROOT},
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for path in findings:
            if path.exists():
                path.unlink()
        for directory in directories:
            if directory.exists():
                try:
                    directory.rmdir()
                except OSError:
                    pass

    remaining = release_residue(PROJECT_ROOT)
    if remaining:
        print("release workspace still contains residue:")
        for path in remaining[:200]:
            print(f"- {path.relative_to(PROJECT_ROOT).as_posix()}")
        if len(remaining) > 200:
            print(f"... and {len(remaining) - 200} more")
        return 1

    print("release workspace clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
