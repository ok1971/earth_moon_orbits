"""Build earth-moon-orbits.html from src/app.html and the language files in src/locales/.

Usage:
  .venv\\Scripts\\python tools\\build.py

Each src/locales/<code>.json holds everything that differs between languages. The languages are
ordered in the language menu by meta.order (languages without one come last, by code). The result
is a single self-contained HTML file, like the original, that opens by double-clicking and can be
published as it is. The build also writes index.html, the entry page of the GitHub Pages site,
which forwards to the page.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'src' / 'app.html'
LOCALES = ROOT / 'src' / 'locales'
OUTPUT = ROOT / 'earth-moon-orbits.html'
ENTRY = ROOT / 'index.html'
MARKER = '/*@LOCALE_DATA@*/ {}'
CSS_MARKER = '  /*@LOCALE_CSS@*/\n'
META_MARKER = '<!--@META@-->\n'
BASE = 'ja'                     # the source language every other file is translated from
REQUIRED_META = ('name', 'locale')
LARGE_NUMBER_STYLES = ('myriad', 'indian')
PLURAL_CATEGORIES = {'zero', 'one', 'two', 'few', 'many', 'other'}   # as returned by Intl.PluralRules
NOTE_FIELDS = {'note', 'maxWidth', 'onlyWithSolarTerms', 'fallbackOnly'}
# Where the page is published; link previews need absolute addresses
SITE_URL = 'https://ok1971.github.io/earth_moon_orbits/'
PREVIEW_IMAGE = 'images/preview.png'      # 1200 × 630, shown when a link to the page is shared
PREVIEW_SIZE = (1200, 630)


def fallback_lang(template=None):
    """The language the page falls back to (FALLBACK_LANG in src/app.html)."""
    template = template or TEMPLATE.read_text(encoding='utf-8')
    m = re.search(r"const FALLBACK_LANG = '([\w-]+)'", template)
    if not m:
        sys.exit(f'{TEMPLATE.name} must define FALLBACK_LANG')
    return m.group(1)


def string_errors(name, strings):
    """A string is text, a list of texts, or plural forms {"one": ..., "other": ...}."""
    errors = []
    for key, value in strings.items():
        if isinstance(value, list):
            ok = all(isinstance(s, str) for s in value)
        elif isinstance(value, dict):
            ok = set(value) <= PLURAL_CATEGORIES and 'other' in value and all(isinstance(s, str) for s in value.values())
        else:
            ok = isinstance(value, str)
        if not ok:
            errors.append(f'{name}: strings.{key} must be text, a list of texts, or plural forms '
                          f'using {", ".join(sorted(PLURAL_CATEGORIES))} and including "other"')
    return errors


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
        if meta.get('dir', 'ltr') not in ('ltr', 'rtl'):
            errors.append(f'{path.name}: meta.dir must be "ltr" or "rtl"')
        big = meta.get('largeNumbers')
        if big and big.get('style') not in LARGE_NUMBER_STYLES:
            errors.append(f'{path.name}: meta.largeNumbers.style must be one of {", ".join(LARGE_NUMBER_STYLES)}')
        if big and big.get('style') == 'myriad' and len(big.get('units', [])) != 2:
            errors.append(f'{path.name}: meta.largeNumbers.units needs the words for 10^8 and 10^4')
        errors += [f'{path.name}: "{k}" is missing' for k in ('strings', 'places') if not data.get(k)]
        errors += string_errors(path.name, data.get('strings', {}))
        if 'notes' in data and path.stem != BASE:
            errors.append(f'{path.name}: notes for translators belong in {BASE}.json only')
        found[path.stem] = data
    if BASE not in found:
        errors.append(f'the base language file {BASE}.json is missing')
    else:
        base_places = set(found[BASE].get('places', {}))
        for code, data in found.items():
            if missing := base_places - set(data.get('places', {})):
                errors.append(f'{code}.json: places missing {", ".join(sorted(missing))}')
        base_strings = found[BASE].get('strings', {})
        for key, note in found[BASE].get('notes', {}).items():
            if key not in base_strings:
                errors.append(f'{BASE}.json: notes.{key} has no string with that key')
            if extra := set(note) - NOTE_FIELDS:
                errors.append(f'{BASE}.json: notes.{key} has unknown fields {", ".join(sorted(extra))}')
    if errors:
        sys.exit('Cannot build:\n  ' + '\n  '.join(errors))
    order = lambda code: (found[code]['meta'].get('order', float('inf')), code)
    return {code: found[code] for code in sorted(found, key=order)}


def locale_css(locales):
    """CSS rules for the typographic settings in each language's meta."""
    rules = []
    for code, data in locales.items():
        meta, sel = data['meta'], f':root[lang="{code}"]'
        props = [f'--{var}: {meta[key]};' for key, var in (('fontUI', 'font-ui'), ('fontTitle', 'font-title')) if meta.get(key)]
        if props:
            rules.append(f'{sel} {{ {" ".join(props)} }}')
        if meta.get('titleLetterSpacing'):
            rules.append(f'{sel} h1 {{ letter-spacing: {meta["titleLetterSpacing"]}; }}')
        if meta.get('joinedScript'):
            # letter-spacing breaks the joined letterforms of scripts such as Arabic and Devanagari
            rules.append(f'{sel} * {{ letter-spacing: 0 !important; }}')
    return ''.join(f'  {r}\n' for r in rules)


def fill_static_text(template, strings):
    """Put the fallback language's text into the elements marked data-i18n, and into <title>, so the
    page reads sensibly before its script runs. The script replaces it with the chosen language."""
    missing = []

    def fill(m):
        value = strings.get(m.group(2))
        if not isinstance(value, str):
            missing.append(m.group(2))
            return m.group(0)
        return m.group(1) + html.escape(value, quote=False) + m.group(3)

    page = re.sub(r'(<[^>]*\bdata-i18n="(\w+)"[^>]*>)(</)', fill, template)
    if missing:
        sys.exit(f'{TEMPLATE.name}: data-i18n keys without text in the fallback language: {", ".join(missing)}')
    return page.replace('<title></title>', f'<title>{html.escape(strings["title"], quote=False)}</title>', 1)


def share_meta(strings):
    """Search-result text and the link preview (Open Graph) shown when the page's address is
    shared. Previews are read without running the page's script, so they are in the fallback
    language."""
    attr = lambda s: html.escape(s, quote=True)
    title, text = strings['title'], strings.get('shareDescription')
    if not text:
        sys.exit('the fallback language needs strings.shareDescription for search results and link previews')
    tags = [f'<meta name="description" content="{attr(text)}">',
            '<meta property="og:type" content="website">',
            f'<meta property="og:title" content="{attr(title)}">',
            f'<meta property="og:description" content="{attr(text)}">',
            f'<meta property="og:url" content="{SITE_URL}">',
            f'<meta property="og:image" content="{SITE_URL}{PREVIEW_IMAGE}">',
            f'<meta property="og:image:width" content="{PREVIEW_SIZE[0]}">',
            f'<meta property="og:image:height" content="{PREVIEW_SIZE[1]}">',
            '<meta name="twitter:card" content="summary_large_image">']
    return ''.join(t + '\n' for t in tags)


def entry_page(lang, strings, meta):
    """index.html: forwards the site's short address to the page, keeping any #language."""
    title, target = html.escape(strings['title'], quote=False), OUTPUT.name
    return (f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
            f'<!-- Generated by tools/build.py: the entry page of the GitHub Pages site -->\n'
            f'<title>{title}</title>\n{meta}'
            f'<meta http-equiv="refresh" content="0; url={target}">\n'
            f"<script>location.replace('{target}' + location.hash);</script>\n"
            f'</head>\n<body>\n<p><a href="{target}">{title}</a></p>\n</body>\n</html>\n')


def build():
    template = TEMPLATE.read_text(encoding='utf-8')
    for marker in (MARKER, CSS_MARKER, META_MARKER):
        if template.count(marker) != 1:
            sys.exit(f'{TEMPLATE.name} must contain {marker.strip()} exactly once')
    fallback = fallback_lang(template)
    locales = load_locales()
    if fallback not in locales:
        sys.exit(f'the fallback language {fallback} has no language file')
    strings = locales[fallback]['strings']
    if not (ROOT / PREVIEW_IMAGE).exists():
        sys.exit(f'the link-preview image {PREVIEW_IMAGE} is missing')
    meta = share_meta(strings)
    template = fill_static_text(template, strings).replace(META_MARKER, meta)
    # The page needs everything except the notes for translators
    shipped = {code: {k: v for k, v in data.items() if k != 'notes'} for code, data in locales.items()}
    # "</" would end the <script> element early if a translation ever contained "</script>"
    data = json.dumps(shipped, ensure_ascii=False, indent=2).replace('</', '<\\/').replace('\n', '\n  ')
    page = template.replace(MARKER, data).replace(CSS_MARKER, locale_css(locales))
    OUTPUT.write_text(page, encoding='utf-8', newline='\n')
    ENTRY.write_text(entry_page(fallback, strings, meta), encoding='utf-8', newline='\n')
    print(f'{OUTPUT.name}: {len(locales)} languages ({", ".join(locales)}); {ENTRY.name} forwards to it')


if __name__ == '__main__':
    build()
