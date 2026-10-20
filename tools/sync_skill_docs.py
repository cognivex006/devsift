"""Copy consumer documentation into the portable skill, without maintainer rules."""
from pathlib import Path
import argparse
import os
import re


def expected(root):
    docs = root / 'docs'
    files = sorted([*docs.glob('*.md'), *docs.glob('reference/*.md'), *docs.glob('cases/*.md')])
    result = {}
    for source in files:
        relative = source.relative_to(docs)
        text = source.read_text(encoding='utf-8')
        def link(match):
            target = match[2]
            if '://' in target or target.startswith(('#', 'mailto:')):
                return match[0]
            path, sep, anchor = target.partition('#')
            resolved = (source.parent / path).resolve()
            if resolved in files:
                return match[0]
            repo_path = os.path.relpath(resolved, root).replace('\\', '/')
            return '[' + match[1] + '](https://github.com/cognivex006/devsift/blob/main/' + repo_path + (sep + anchor if sep else '') + ')'
        result[relative] = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    return result


def sync(root, check=False):
    root = Path(root).resolve()
    destination = root / 'skills/devsift/references'
    files = expected(root)
    current = {p.relative_to(destination): p.read_text(encoding='utf-8')
               for p in destination.rglob('*.md')} if destination.exists() else {}
    if check:
        if files != current:
            raise SystemExit('Skill references are stale. Run python tools/sync_skill_docs.py')
        return
    for name in current.keys() - files.keys():
        (destination / name).unlink()
    for name, text in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    sync(Path(__file__).resolve().parents[1], parser.parse_args().check)
