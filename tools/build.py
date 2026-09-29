"""Build earth-moon-orbits.html from src/app.html and the language files in src/locales/.

Usage:
  .venv\\Scripts\\python tools\\build.py

Each src/locales/<code>.json holds everything that differs between languages. The languages are
ordered in the language menu by meta.order (languages without one come last, by code). The result
is a single self-contained HTML file, like the original, that opens by double-clicking and can be
published as it is.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'src' / 'app.html'
LOCALES = ROOT / 'src' / 'locales'
OUTPUT = ROOT / 'earth-moon-orbits.html'
MARKER = '/*@LOCALE_DATA@*/ {}'
BASE = 'ja'                     # the source language every other file is translated from
REQUIRED_META = ('name', 'locale')


def load_locales():
    """Read every language file; return {code: data} in language-menu order, or exit on errors."""
    found, errors = {}, []
    for path in sorted(LOCALES.glob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errors.append(f'{path.name}: not valid JSON ({e})')
            continue
        meta = data.get('meta', {})
        errors += [f'{path.name}: meta.{k} is missing' for k in REQUIRED_META if not meta.get(k)]
        errors += [f'{path.name}: "{k}" is missing' for k in ('strings', 'places') if not data.get(k)]
        found[path.stem] = data
    if BASE not in found:
        errors.append(f'the base language file {BASE}.json is missing')
    else:
        base_places = set(found[BASE].get('places', {}))
        for code, data in found.items():
            if missing := base_places - set(data.get('places', {})):
                errors.append(f'{code}.json: places missing {", ".join(sorted(missing))}')
    if errors:
        sys.exit('Cannot build:\n  ' + '\n  '.join(errors))
    order = lambda code: (found[code]['meta'].get('order', float('inf')), code)
    return {code: found[code] for code in sorted(found, key=order)}


def build():
    template = TEMPLATE.read_text(encoding='utf-8')
    if template.count(MARKER) != 1:
        sys.exit(f'{TEMPLATE.name} must contain {MARKER} exactly once')
    locales = load_locales()
    # "</" would end the <script> element early if a translation ever contained "</script>"
    data = json.dumps(locales, ensure_ascii=False, indent=2).replace('</', '<\\/').replace('\n', '\n  ')
    OUTPUT.write_text(template.replace(MARKER, data), encoding='utf-8', newline='\n')
    print(f'{OUTPUT.name}: {len(locales)} languages ({", ".join(locales)})')


if __name__ == '__main__':
    build()
