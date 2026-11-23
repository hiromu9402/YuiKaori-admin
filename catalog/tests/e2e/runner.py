"""公開ページを headless Chromium で開いて、表示結果を取り出す。

    build_site(): 公開ページの HTML/JS と JSON を一時ディレクトリにまとめる
    serve():      そのディレクトリを 127.0.0.1 の空いているポートで配信する
    run_probe():  probe.js で各ページの表示結果を集め、dict で返す

期待値（fixtures/expected/frontend.json）を作り直すときは、DB 化する前の HTML と JSON で実行する:
    .venv/bin/python -m catalog.tests.e2e.runner --baseline <旧版のサイトのディレクトリ>
"""
import contextlib
import functools
import html
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADMIN_DIR = HERE.parents[2]  # catalog/tests/e2e → このリポジトリの直下
# 公開サイトのリポジトリ（HTML/JS を読む）。settings.SITE_DIR と同じく、既定は隣の database_yuikaori/
SITE_DIR = Path(os.environ.get("YUIKAORI_SITE_DIR") or ADMIN_DIR.parent / "database_yuikaori")
EXPECTED_FILE = HERE.parent / "fixtures" / "expected" / "frontend.json"
PROBES = [("index", None), ("tour", None), ("checklist", "my.html"), ("checklist", "my_c.html"),
          ("checklist", "my_f.html"), ("calendar", None), ("event", None), ("sub", None)]


def chromium_path():
    return os.environ.get("CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser")


# 公開サイトの許可リスト（公開サイトのリポジトリの tools/site_files.py、catalog/preview.py と同じ）。
# このファイルは Django なしでも動かす（--baseline）ので、ここに書く
ALLOWED = [
    re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(html|css|js|json)$"),
    re.compile(r"^sub/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.html$"),
]


def allowed(relpath):
    return any(p.match(relpath) for p in ALLOWED)


def site_pages(html_dir):
    """公開サイトの HTML・CSS・JS（許可リストに合うもの。JSON は除く）の相対パス。"""
    html_dir = Path(html_dir)
    files = [p for p in html_dir.iterdir() if p.is_file()]
    if (html_dir / "sub").is_dir():
        files += [p for p in (html_dir / "sub").iterdir() if p.is_file()]
    paths = (p.relative_to(html_dir).as_posix() for p in files)
    return sorted(p for p in paths if allowed(p) and not p.endswith(".json"))


def build_site(dest, html_dir=SITE_DIR, json_dir=SITE_DIR):
    dest = Path(dest)
    # ページやスクリプトが増えても写し漏れがないよう、決まった一覧ではなく許可リストに合うものをすべて写す
    for name in site_pages(html_dir):
        (dest / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(html_dir) / name, dest / name)
    for src in Path(json_dir).glob("*.json"):
        shutil.copy(src, dest / src.name)
    shutil.copy(HERE / "probe.js", dest / "__probe.js")
    (dest / "__probe.html").write_text(
        '<!DOCTYPE html><meta charset="utf-8"><body><script src="__probe.js"></script></body>', encoding="utf-8")


@contextlib.contextmanager
def serve(directory):
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def run_probe(base_url, page, target=None, timeout=240):
    url = f"{base_url}/__probe.html?page={page}" + (f"&target={target}" if target else "")
    with tempfile.TemporaryDirectory(dir=Path.home() / "snap" / "chromium" / "common"
                                     if (Path.home() / "snap" / "chromium" / "common").exists() else None) as profile:
        proc = subprocess.run(
            [chromium_path(), "--headless", "--no-sandbox", "--disable-gpu", f"--user-data-dir={profile}",
             "--virtual-time-budget=600000", "--dump-dom", url],
            capture_output=True, text=True, timeout=timeout)
    found = re.search(r'<pre id="result">(.*?)</pre>', proc.stdout, re.S)
    if not found:
        raise RuntimeError(f"{page}: 結果を取得できませんでした\n{proc.stderr[-2000:]}")
    result = json.loads(html.unescape(found.group(1)))
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"{page}: {result['error']}")
    return result


def collect(site_dir):
    results = {}
    with serve(site_dir) as base_url:
        for page, target in PROBES:
            results[target or page] = run_probe(base_url, page, target)
    return results


if __name__ == "__main__":
    if sys.argv[1:2] != ["--baseline"] or len(sys.argv) != 3:
        sys.exit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        build_site(tmp, html_dir=sys.argv[2], json_dir=sys.argv[2])
        data = collect(tmp)
    EXPECTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXPECTED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{EXPECTED_FILE} に書き出しました")
