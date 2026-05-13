from __future__ import annotations

import collections
import pathlib
import re
import sys


def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'app/static/app.js')
    text = path.read_text(encoding='utf-8')
    names = re.findall(r'function\s+([A-Za-z0-9_]+)\s*\(', text)
    counts = collections.Counter(names)
    dupes = [(name, count) for name, count in counts.items() if count > 1]
    dupes.sort(key=lambda x: (-x[1], x[0]))
    print(f'File: {path}')
    print(f'Total named functions: {len(names)}')
    print(f'Duplicate definitions: {len(dupes)}')
    for name, count in dupes:
        print(f'{count:>2}x  {name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
