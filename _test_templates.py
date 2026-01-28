from jinja2 import Environment, FileSystemLoader
from pathlib import Path

env = Environment(loader=FileSystemLoader('templates'))
templates = sorted([f.name for f in Path('templates').glob('*.html') if not f.name.startswith('_')])

print(f'Testing {len(templates)} templates...\n')
errors = []
ok = []

for t in templates:
    try:
        env.get_template(t)
        ok.append(t)
        print(f'✓ {t}')
    except Exception as e:
        errors.append((t, str(e)))
        print(f'✗ {t}: {str(e)[:80]}...')

print(f'\n{len(ok)}/{len(templates)} OK, {len(errors)} ERRORS')
if errors:
    print('\nErrors:')
    for t, e in errors:
        print(f'  {t}: {e[:100]}')
