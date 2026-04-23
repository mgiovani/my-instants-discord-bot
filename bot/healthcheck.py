from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _path() -> Path:
    return Path(
        os.environ.get(
            'MYINSTANTS_HEARTBEAT_FILE',
            '/tmp/myinstants-heartbeat',  # noqa: S108
        )
    )


def _max_age_seconds() -> float:
    return float(os.environ.get('MYINSTANTS_HEARTBEAT_MAX_AGE_SECONDS', '90'))


def main() -> int:
    heartbeat = _path()
    if not heartbeat.exists():
        print(f'healthcheck: {heartbeat} missing', file=sys.stderr)
        return 1
    age = time.time() - heartbeat.stat().st_mtime
    max_age = _max_age_seconds()
    if age > max_age:
        print(
            f'healthcheck: heartbeat is {age:.0f}s old (> {max_age:.0f}s)',
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
