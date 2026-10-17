"""Check local documentation links, public command spelling and portable skill sync."""
from pathlib import Path
import re

if __package__:
    from .sync_skill_docs import sync
else:
    from sync_skill_docs import sync


def check(root):
    root = Path(root).resolve()
    files = sorted([*root.glob('*.md'), *(root / 'docs').rglob('*.md'),
                    *(root / 'skills').rglob('*.md')])
    errors = []
    for path in files:
        text = path.read_text(encoding='utf-8')
        if re.search(r'\b(?:REQ|FR|NFR)[-_ ]?\d+\b|\b[GT]\d{3}\b', text, re.I):
            errors.append(f'{path.relative_to(root)}: replace planning identifiers with capability names')
        if re.search(r'python\S*(?:\s+-[\w-]+)*\s+-m\s+devsift\b', text):
            errors.append(f'{path.relative_to(root)}: use the public devsift command')
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if re.match(r'[a-z]+://|mailto:|#', target):
                continue
            local = target.split('#')[0]
            if local and not (path.parent / local).exists():
                errors.append(f'{path.relative_to(root)}: missing local link {local}')
    sync(root, check=True)
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Documentation checks passed ({len(files)} Markdown files).')


if __name__ == '__main__':
    check(Path(__file__).resolve().parents[1])
