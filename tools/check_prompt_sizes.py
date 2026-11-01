#!/usr/bin/env python3
"""UTF-8 byte limits for inline host prompts, including standalone ZIPs."""
from pathlib import Path
from zipfile import ZipFile
import argparse
import io
import json

SKILL_LIMIT = 48128
AGENT_LIMIT = 51200
AGENT_WARNING = 49152


def measure(path, data, kind):
    size = len(data)
    limit = AGENT_LIMIT if kind == 'agent' else SKILL_LIMIT
    status = 'FAIL' if size > limit else 'WARN' if kind == 'agent' and size > AGENT_WARNING else 'PASS'
    return {'path': path, 'kind': kind, 'bytes': size, 'limit': limit, 'status': status}


def inspect_zip(archive, label, standalone=False):
    rows = []
    for item in archive.infolist():
        if item.is_dir():
            continue
        parts = Path(item.filename).parts
        if parts[-1] == 'SKILL.md' and (standalone or len(parts) >= 3 and parts[-3] == 'skills'):
            rows.append(measure(label + '!' + item.filename, archive.read(item), 'standalone_skill' if standalone else 'skill'))
        elif len(parts) >= 2 and parts[-2] == 'agents' and parts[-1].endswith('.md'):
            rows.append(measure(label + '!' + item.filename, archive.read(item), 'agent'))
        elif len(parts) >= 3 and parts[-3] == 'individual-packages' and parts[-1].endswith('.zip'):
            with ZipFile(io.BytesIO(archive.read(item))) as inner:
                rows += inspect_zip(inner, label + '!' + item.filename, standalone=True)
    return rows


def run(root):
    root = Path(root)
    if root.is_file():
        with ZipFile(root) as z:
            standalone = not any('/skills/' in n or n.startswith('skills/') for n in z.namelist())
            rows = inspect_zip(z, root.name, standalone=standalone)
    else:
        rows = [measure(p.relative_to(root).as_posix(), p.read_bytes(), 'skill')
                for p in sorted((root / 'skills').glob('*/SKILL.md'))]
        rows += [measure(p.relative_to(root).as_posix(), p.read_bytes(), 'agent')
                 for p in sorted((root / 'agents').glob('*.md'))]
        for p in sorted((root / 'individual-packages').glob('*/*.zip')):
            with ZipFile(p) as z:
                rows += inspect_zip(z, p.relative_to(root).as_posix(), standalone=True)
    errors = [r for r in rows if r['status'] == 'FAIL']
    if not rows:
        errors.append({'path': str(root), 'error': 'NO_PROMPT_BODIES'})
    return {'pass': not errors, 'limits': {'skill': SKILL_LIMIT, 'agent': AGENT_LIMIT, 'agent_warning_above': AGENT_WARNING},
            'files': rows, 'errors': errors, 'warnings': [r for r in rows if r['status'] == 'WARN']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    report = run(parser.parse_args().root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['pass'] else 1)
