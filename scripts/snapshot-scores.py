#!/usr/bin/env python3
"""
snapshot-scores.py — Save a point-in-time snapshot of all Exodus scores.

Appends to data/score-history.jsonl (one JSON line per snapshot).
Run by the enrich workflow after each enrichment cycle.

Usage: python3 scripts/snapshot-scores.py
"""
import json, os
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_DIR = Path('projects')
HISTORY_FILE = Path('data/score-history.jsonl')

def main():
    import re

    scores = {}
    for md in sorted(PROJECTS_DIR.glob('*.md')):
        with open(md) as f:
            content = f.read()
        m = re.search(r'^exodus_score:\s*(\d+)', content, re.MULTILINE)
        if m:
            scores[md.stem] = int(m.group(1))

    if not scores:
        print('No scores found.', flush=True)
        return

    snapshot = {
        'ts': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'total': len(list(PROJECTS_DIR.glob('*.md'))),
        'scanned': len(scores),
        'avg': round(sum(scores.values()) / len(scores), 2),
        'distribution': {str(i): sum(1 for s in scores.values() if s == i) for i in range(11)},
        'top': sorted(scores.items(), key=lambda x: -x[1])[:10],
    }

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, 'a') as f:
        f.write(json.dumps(snapshot) + '\n')

    print(f'Snapshot: {snapshot["scanned"]} scanned, avg {snapshot["avg"]}, '
          f'saved to {HISTORY_FILE}', flush=True)

if __name__ == '__main__':
    main()
