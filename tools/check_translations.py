"""src/locales/ の各言語の訳文が、日本語の原文（ja.json）の意味を正しく伝えているかを Claude に確認させる。

使い方:
  .venv\\Scripts\\python tools\\check_translations.py             # すべての言語
  .venv\\Scripts\\python tools\\check_translations.py ko fr       # 指定した言語だけ
  .venv\\Scripts\\python tools\\check_translations.py --dry-run   # API を呼ばず、機械的なチェックだけ

API キーは .env の ANTHROPIC_API_KEY から読み込む。結果は translation-report.md に書き出す。
"""
import argparse
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from build import BASE, load_locales

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / 'translation-report.md'
MODEL = 'claude-opus-5'
PRICE_PER_MTOK = (5.00, 25.00)   # claude-opus-5 の入力・出力 [USD / 100万トークン]

LANG_NAMES_JA = {
    'en': '英語', 'zh-Hans': '中国語（簡体字）', 'zh-Hant': '中国語（繁体字）', 'ko': '韓国語',
    'es': 'スペイン語', 'pt': 'ポルトガル語', 'fr': 'フランス語', 'ru': 'ロシア語',
    'id': 'インドネシア語', 'hi': 'ヒンディー語', 'ar': 'アラビア語',
}
SEVERITY_JA = {'error': '誤り', 'warning': '要確認'}
PLACEHOLDER = re.compile(r'\{(\w+)\}')
# 二十四節気は日本語・中国語・韓国語（SEKKI がある言語）でしか表示しない
SEKKI_ONLY_KEYS = {'tgSekki', 'sekkiRange'}


# ---- .env ------------------------------------------------------------------
def load_dotenv(path):
    """KEY=VALUE 形式の行を環境変数に入れる（すでに設定されている変数は上書きしない）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip().removeprefix('export ').strip()
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


# ---- 言語ファイルを読む ------------------------------------------------------------
def read_tables():
    """src/locales/*.json を、チェックで使う形にまとめる。"""
    data = load_locales()
    for code, d in data.items():
        LANG_NAMES_JA.setdefault(code, d['meta']['name'])
    return {
        'LANGS': list(data),
        'LOCALES': {c: d['meta']['locale'] for c, d in data.items()},
        'SEKKI': {c: d['solarTerms'] for c, d in data.items() if 'solarTerms' in d},
        'DICT': {c: d['strings'] for c, d in data.items()},
        'PLACES': {c: d['places'] for c, d in data.items()},
    }


# ---- 機械的なチェック ----------------------------------------------------------
def placeholders(v):
    text = ' '.join(map(str, v)) if isinstance(v, list) else str(v)
    return sorted(PLACEHOLDER.findall(text))


def used_keys(tables, lang):
    """その言語の画面で実際に使う、日本語側のキー。"""
    return [k for k in tables['DICT'][BASE] if lang in tables['SEKKI'] or k not in SEKKI_ONLY_KEYS]


def mechanical_checks(tables, lang):
    base, target = tables['DICT'][BASE], tables['DICT'][lang]
    notes = []
    if missing := [k for k in used_keys(tables, lang) if k not in target]:
        notes.append('日本語にあって訳に無いキー: ' + ', '.join(f'`{k}`' for k in missing))
    for key, ja in base.items():
        if key not in target:
            continue
        tr = target[key]
        if isinstance(ja, list) or isinstance(tr, list):
            if not (isinstance(ja, list) and isinstance(tr, list) and len(ja) == len(tr)):
                notes.append(f'`{key}`: 配列の形が日本語と違います')
                continue
        if placeholders(ja) != placeholders(tr):
            notes.append(f'`{key}`: プレースホルダが違います（日本語 {placeholders(ja)}、訳 {placeholders(tr)}）')
    return notes


def build_items(tables, lang):
    """LLM に渡す「キー・原文・訳文」の組を作る。"""
    base, target = tables['DICT'][BASE], tables['DICT'][lang]
    items = [{'key': k, 'ja': base[k], 'target': target[k]} for k in used_keys(tables, lang) if k in target]
    if lang in tables['SEKKI']:
        items.append({'key': 'SEKKI', 'ja': tables['SEKKI'][BASE], 'target': tables['SEKKI'][lang]})
    for pid, ja in tables['PLACES'][BASE].items():
        items.append({'key': f'PLACES.{pid}', 'ja': ja, 'target': tables['PLACES'][lang].get(pid, '')})
    return items


# ---- Claude による確認 ---------------------------------------------------------
class Issue(BaseModel):
    key: str = Field(description='問題のある項目の key')
    severity: Literal['error', 'warning']
    problem: str = Field(description='何がどう問題かの説明（日本語）')
    suggestion: str = Field(description='修正後の訳文（訳文の言語で）')


class Review(BaseModel):
    summary: str = Field(description='この言語の翻訳全体の評価（日本語で 2〜3 文）')
    issues: list[Issue]


def system_prompt(lang, locale):
    name = f'{LANG_NAMES_JA[lang]}（ロケール {locale}）'
    return f"""あなたは天文学に詳しいプロの翻訳レビュアーです。
Web アプリ「地球と月の公転軌道」は、太陽のまわりを回る地球と月をアニメーションで示す教育用の天文シミュレーションです。その UI テキストについて、日本語の原文（ja）と{name}の訳文（target）を照らし合わせ、訳文が原文の意味を正しく伝えているかを確認してください。

確認すること:
- 意味の誤り、訳し漏れ、原文に無い情報の追加
- 天文用語の誤り（近日点、黄経、黄緯、離角、交点、近点年、二十四節気など）
- 数値・単位・記号の食い違い
- {{n}} や {{place}} などのプレースホルダ（実行時に値が入る）が保たれているか。語順に合わせて位置が変わるのは問題ありません
- 同じ概念の訳語が項目間でぶれていないか
- その言語の話者にとって不自然で、意味が伝わりにくい表現

問題にしないこと:
- 意味が同じで、表現が違うだけのもの（直訳である必要はありません）
- 日本特有の表現を、その言語で自然な言い方に置き換えたもの。たとえば月の満ち欠けの「十三夜のころ」「有明の月」を、その言語の標準的な天文用語で訳すのは正しい対応です
- ボタンやラベルを短くするための、意味を損なわない省略
- 好みの問題にすぎない言い回し

入力について:
- 配列（seasons4、phases、compass など）は配列全体で 1 項目です
- SEKKI は二十四節気（春分から順）、PLACES.* は観測地の都市名です

図と表示についての前提:
- 真上から見た図と真横から見た図では、右が春分点（黄経0°）の方向、上が黄経90°の方向です。そのため地球は、春分のころ左端、秋分のころ右端にいます。「春分」「秋分」（その時期、またはそのときの地球の位置）と「春分点」「秋分点」（天球上の方向）を取り違えた訳は誤りです
- seasons4 は図の上で日付と並べて表示されます（例: "Equinox 20 Mar"）。月名が無くても区別できるので、問題にしないでください
- dirRight・dirLeft の括弧内「（秋分側）」「（春分側）」は、日本語・中国語・韓国語以外の言語では秋分点・春分点の方向と誤解されやすいため、意図的に省いています。問題にしないでください
- 二十四節気は日本語・中国語・韓国語でしか表示しません

出力について:
- issues には問題のある項目だけを入れます。問題が無ければ空の配列にしてください
- severity は、意味が違う・抜けている・誤った情報を伝えるものを "error"、意味はおおむね合っているが不正確・不自然・訳語がぶれているものを "warning" にします
- problem は日本語で、原文と訳文のどこがどう違うのかを具体的に書きます
- suggestion には修正後の訳文を{LANG_NAMES_JA[lang]}で書きます
- summary には、この言語の翻訳全体の評価を日本語で 2〜3 文で書きます"""


def review(client, lang, locale, items):
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        betas=['server-side-fallback-2026-07-01'],
        fallbacks='default',   # 安全分類器に断られたときは、推奨モデルでサーバー側が再実行する
        thinking={'type': 'adaptive'},
        system=system_prompt(lang, locale),
        messages=[{'role': 'user', 'content': json.dumps(items, ensure_ascii=False, indent=1)}],
        output_format=Review,
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == 'refusal':
        raise RuntimeError('モデルが応答を拒否しました')
    if message.stop_reason == 'max_tokens':
        raise RuntimeError('出力が max_tokens に達して途中で切れました')
    return message.parsed_output, message.usage


# ---- レポート ----------------------------------------------------------------
def show(v):
    return ' / '.join(map(str, v)) if isinstance(v, list) else str(v)


def write_report(langs, results, usage_total):
    lines = [
        '# 翻訳チェック結果', '',
        '- 対象: `src/locales/*.json`（原文は日本語の ja.json）',
        f'- モデル: `{MODEL}`',
        f'- 実行日時: {datetime.now():%Y-%m-%d %H:%M}',
        f'- トークン: 入力 {usage_total[0]:,} ・ 出力 {usage_total[1]:,}（費用の目安 ${cost(usage_total):.2f}）', '',
        '| 言語 | 誤り | 要確認 | 機械チェック |', '|---|---:|---:|---:|',
    ]
    for lang in langs:
        r = results[lang]
        issues = r['review'].issues if r.get('review') else []
        n_err = sum(i.severity == 'error' for i in issues)
        n_warn = len(issues) - n_err
        failed = ' (LLM 失敗)' if r.get('error') else ''
        lines.append(f'| {LANG_NAMES_JA[lang]}（{lang}）{failed} | {n_err} | {n_warn} | {len(r["notes"])} |')

    for lang in langs:
        r = results[lang]
        by_key = {item['key']: item for item in r['items']}
        lines += ['', f'## {LANG_NAMES_JA[lang]}（{lang}）', '']
        if r.get('error'):
            lines += [f'> LLM による確認に失敗しました: {r["error"]}', '']
        elif r.get('review'):
            lines += [r['review'].summary, '']
        if r['notes']:
            lines += ['### 機械的なチェック', ''] + [f'- {n}' for n in r['notes']] + ['']
        if not r.get('review'):
            continue
        issues = sorted(r['review'].issues, key=lambda i: i.severity != 'error')
        if not issues:
            lines += ['指摘はありません。']
        for issue in issues:
            item = by_key.get(issue.key)
            lines += [f'### `{issue.key}` — {SEVERITY_JA[issue.severity]}', '']
            if item:
                lines += [f'- 原文: {show(item["ja"])}', f'- 現在の訳: {show(item["target"])}']
            lines += [f'- 問題点: {issue.problem}', f'- 修正案: {issue.suggestion}', '']
    REPORT.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')


def cost(usage_total):
    return sum(n * p for n, p in zip(usage_total, PRICE_PER_MTOK)) / 1_000_000


# ---- main ------------------------------------------------------------------
def main():
    sys.stdout.reconfigure(errors='replace')
    tables = read_tables()
    all_langs = [l for l in tables['LANGS'] if l != BASE and l in tables['DICT']]

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('langs', nargs='*', metavar='LANG', help=f'確認する言語（省略時はすべて）: {" ".join(all_langs)}')
    parser.add_argument('--dry-run', action='store_true', help='API を呼ばず、機械的なチェックだけを表示する')
    parser.add_argument('--jobs', type=int, default=3, help='同時に確認する言語の数（既定 3）')
    args = parser.parse_args()
    if unknown := [l for l in args.langs if l not in all_langs]:
        parser.error(f'不明な言語: {" ".join(unknown)}（使える言語: {" ".join(all_langs)}）')
    langs = args.langs or all_langs

    results = {}
    for lang in langs:
        results[lang] = {'notes': mechanical_checks(tables, lang), 'items': build_items(tables, lang)}
        print(f'{lang}: 確認する項目 {len(results[lang]["items"])} 件、機械チェックの指摘 {len(results[lang]["notes"])} 件')
        for note in results[lang]['notes']:
            print(f'    - {note}')
    if args.dry_run:
        return

    load_dotenv(ROOT / '.env')
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key or not key.isascii():
        sys.exit('.env の ANTHROPIC_API_KEY にキーが設定されていません（仮の文字列のままかもしれません）')
    client = anthropic.Anthropic(max_retries=5)

    usage_total = [0, 0]
    lock = threading.Lock()

    def run(lang):
        print(f'{lang}: Claude に確認させています…', flush=True)
        try:
            result, usage = review(client, lang, tables['LOCALES'][lang], results[lang]['items'])
        except anthropic.AuthenticationError:
            results[lang]['error'] = 'API キーが無効です（.env を確認してください）'
        except anthropic.APIStatusError as e:
            results[lang]['error'] = f'API エラー {e.status_code}: {e.message}'
        except anthropic.APIConnectionError:
            results[lang]['error'] = 'API に接続できませんでした'
        except RuntimeError as e:
            results[lang]['error'] = str(e)
        else:
            results[lang]['review'] = result
            with lock:
                usage_total[0] += usage.input_tokens
                usage_total[1] += usage.output_tokens
        if 'error' in results[lang]:
            print(f'{lang}: 失敗 - {results[lang]["error"]}', flush=True)
        else:
            print(f'{lang}: 完了（指摘 {len(results[lang]["review"].issues)} 件）', flush=True)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(run, langs))

    write_report(langs, results, usage_total)
    print(f'\n{REPORT.name} に書き出しました。費用の目安 ${cost(usage_total):.2f}'
          f'（入力 {usage_total[0]:,} ・ 出力 {usage_total[1]:,} トークン）')


if __name__ == '__main__':
    main()
