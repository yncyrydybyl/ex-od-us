#!/usr/bin/env python3
"""
migrate-to-matrix-links.py — Convert legacy matrix_rooms to structured matrix_links.

Reads each project file, finds matrix_rooms, builds equivalent matrix_links
records, writes them back. Preserves matrix_rooms for backward compat.
"""
import re, sys
from pathlib import Path

PROJECTS_DIR = Path('projects')

def parse_target(url):
    """Extract Matrix entity ID from a matrix.to URL."""
    m = re.search(r'matrix\.to/#/([#@+][^?/\s]+)', url)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    return None

def main():
    migrated = 0
    skipped = 0
    for fpath in sorted(PROJECTS_DIR.glob('*.md')):
        content = fpath.read_text()

        # Skip if already migrated
        if 'matrix_links:' in content:
            skipped += 1
            continue

        # Find matrix_rooms — both multiline and inline list formats
        room_lines = []
        # Multi-line: matrix_rooms:\n  - "..."
        ml = re.search(r'^matrix_rooms:\s*\n((?:  - "?[^"\n]*"?\s*\n)+)', content, re.MULTILINE)
        if ml:
            room_lines = re.findall(r'  - "?([^"\n]+?)"?\s*$', ml.group(1), re.MULTILINE)
        else:
            # Inline: matrix_rooms: [url1, url2]
            il = re.search(r'^matrix_rooms:\s*\[([^\]]+)\]', content, re.MULTILINE)
            if il:
                room_lines = [x.strip().strip('"').strip("'") for x in il.group(1).split(',') if x.strip()]

        if not room_lines:
            skipped += 1
            continue

        # Build matrix_links records
        links = []
        for url in room_lines:
            target = parse_target(url)
            if not target:
                continue
            kind = 'room' if target.startswith('#') else ('user' if target.startswith('@') else 'space')
            homeserver = target.split(':', 1)[1] if ':' in target else ''
            via = 'matrix.to' if 'matrix.to' in url else 'unknown'
            # Default quality: matrix.to + anchor (since extracted from URL list)
            quality = 7 if via == 'matrix.to' else 5
            links.append({
                'target': target,
                'kind': kind,
                'via': via,
                'source': 'anchor',
                'homeserver': homeserver,
                'quality': quality,
            })

        if not links:
            skipped += 1
            continue

        # Sort by quality desc
        links.sort(key=lambda l: (-l['quality'], l['target'].lower()))

        # Build YAML representation
        link_yaml_lines = ['matrix_links:']
        for l in links:
            link_yaml_lines.append(f'  - target: "{l["target"]}"')
            link_yaml_lines.append(f'    kind: {l["kind"]}')
            link_yaml_lines.append(f'    via: {l["via"]}')
            link_yaml_lines.append(f'    source: {l["source"]}')
            link_yaml_lines.append(f'    quality: {l["quality"]}')
        link_yaml = '\n'.join(link_yaml_lines) + '\n'

        # Insert matrix_links before matrix_rooms
        new_content = content.replace('matrix_rooms:', link_yaml + 'matrix_rooms:', 1)
        fpath.write_text(new_content)
        migrated += 1

        if migrated % 100 == 0:
            print(f'  {migrated} migrated...', flush=True)

    print(f'Done: {migrated} migrated, {skipped} skipped (no rooms or already migrated)')

if __name__ == '__main__':
    main()
