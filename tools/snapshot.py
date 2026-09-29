"""Screenshot the page in every language and compare two sets of screenshots.

Usage:
  .venv\\Scripts\\python tools\\snapshot.py take OUTDIR [--html FILE] [--langs ja en ...]
  .venv\\Scripts\\python tools\\snapshot.py compare DIR_A DIR_B

"take" opens a copy of the page in headless Microsoft Edge for each language, paused at a fixed
time and place (6 May 2027 11:00 UTC, Tokyo), and saves OUTDIR/<lang>.png. "compare" reports
which screenshots differ and where. Use it to check that a change to the code or the language
files changes only what it should.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / 'earth-moon-orbits.html'
ANCHOR = '  requestAnimationFrame(frame);\n})();'
WINDOW = '1400,1800'
WAIT_MS = 4000                  # real time to wait for fonts and a few frames before the shot
STORE_KEY = 'earth-moon-orbits:settings'


def find_edge():
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles')):
        if base and (p := Path(base) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe').exists():
            return p
    sys.exit('Microsoft Edge was not found')


def wait_for_file(path, timeout):
    """Wait until PATH exists and its size stops changing. The msedge.exe we start hands off to a
    browser process and returns before that process has written the screenshot."""
    end, last = time.monotonic() + timeout, -1
    while time.monotonic() < end:
        size = path.stat().st_size if path.exists() else -1
        if size > 0 and size == last:
            return True
        last = size
        time.sleep(0.5)
    return False


def languages(src):
    """Language codes in menu order, read from the LOCALE_DATA the build inserted."""
    start = src.index('const LOCALE_DATA = ') + len('const LOCALE_DATA = ')
    data, _ = json.JSONDecoder().raw_decode(src, start)
    return list(data)


def take(outdir, html, langs):
    src = html.read_text(encoding='utf-8').replace('\r\n', '\n')
    if src.count(ANCHOR) != 1:
        sys.exit(f'{html.name}: cannot find the start of the main loop')
    langs = langs or languages(src)
    outdir.mkdir(parents=True, exist_ok=True)
    pages, profile = outdir / '_pages', outdir / '_profile'
    pages.mkdir(exist_ok=True)
    setup = ('  state.t = daysFromMs(Date.UTC(2027, 4, 6, 11));\n'
             '  state.trailStart = state.t - 90;\n'
             '  state.playing = false;\n'
             '  dirty = true;\n')
    edge = find_edge()
    # Web fonts load from Google at unpredictable moments, so the copies block them and render with
    # the system fonts in each font stack: the shots then compare layout, text and drawing exactly
    no_web_fonts = '<meta http-equiv="Content-Security-Policy" content="style-src \'unsafe-inline\'; font-src \'none\'">\n'
    for lang in langs:
        preset = f"<script>localStorage.setItem('{STORE_KEY}', JSON.stringify({{ lang: '{lang}', placeId: 'tokyo' }}));</script>\n"
        page = pages / f'{lang}.html'
        page.write_text(no_web_fonts + src.replace('<script>', preset + '<script>', 1).replace(ANCHOR, setup + ANCHOR),
                        encoding='utf-8', newline='\n')
        shot = outdir / f'{lang}.png'
        shot.unlink(missing_ok=True)
        # A separate profile for every shot: Edge hands a launch that reuses a running profile over
        # to that instance, which then never takes the screenshot
        for attempt in range(2):
            subprocess.run([str(edge), '--headless=new', '--disable-gpu', '--hide-scrollbars',
                            '--no-first-run', '--no-default-browser-check',
                            f'--user-data-dir={profile / f"{lang}-{attempt}"}', f'--window-size={WINDOW}',
                            f'--timeout={WAIT_MS}', f'--screenshot={shot}', page.resolve().as_uri()],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if wait_for_file(shot, WAIT_MS / 1000 + 20):
                break
        print(f'{lang}: {shot if shot.exists() else "FAILED"}')
    shutil.rmtree(profile, ignore_errors=True)


def read_png(path):
    """Decode an 8-bit, non-interlaced RGB or RGBA PNG into (width, height, channels, rows)."""
    data = path.read_bytes()
    pos, idat, info = 8, b'', None
    while pos < len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            info = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT':
            idat += body
        pos += 12 + length
    w, h, depth, color, _, _, interlace = info
    if depth != 8 or color not in (2, 6) or interlace:
        raise ValueError(f'{path.name}: unsupported PNG format')
    ch = 3 if color == 2 else 4
    raw, stride, rows, prev = zlib.decompress(idat), w * ch, [], bytearray(w * ch)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            b, c = prev[i], prev[i - ch] if i >= ch else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, ch, rows


def compare(dir_a, dir_b):
    names = sorted({p.name for p in dir_a.glob('*.png')} | {p.name for p in dir_b.glob('*.png')})
    same = True
    for name in names:
        a, b = dir_a / name, dir_b / name
        if not (a.exists() and b.exists()):
            print(f'{name}: only in {dir_a if a.exists() else dir_b}')
            same = False
            continue
        if a.read_bytes() == b.read_bytes():
            print(f'{name}: identical')
            continue
        wa, ha, ca, ra = read_png(a)
        wb, hb, cb, rb = read_png(b)
        if (wa, ha, ca) != (wb, hb, cb):
            print(f'{name}: different sizes')
            same = False
            continue
        box, count = None, 0
        for y in range(ha):
            if ra[y] == rb[y]:
                continue
            for x in range(wa):
                if ra[y][x * ca:(x + 1) * ca] != rb[y][x * cb:(x + 1) * cb]:
                    count += 1
                    box = (min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)) if box else (x, y, x, y)
        if count:
            same = False
            hint = ('  (one pixel row only: usually rendering noise at a canvas edge; retake to confirm)'
                    if box[1] == box[3] else '')
            print(f'{name}: {count} pixels differ, within x {box[0]}-{box[2]}, y {box[1]}-{box[3]}{hint}')
        else:
            print(f'{name}: identical pixels')
    return same


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('take')
    t.add_argument('outdir', type=Path)
    t.add_argument('--html', type=Path, default=PAGE)
    t.add_argument('--langs', nargs='*')
    c = sub.add_parser('compare')
    c.add_argument('dir_a', type=Path)
    c.add_argument('dir_b', type=Path)
    args = parser.parse_args()
    if args.cmd == 'take':
        take(args.outdir, args.html, args.langs)
    else:
        sys.exit(0 if compare(args.dir_a, args.dir_b) else 1)


if __name__ == '__main__':
    main()
