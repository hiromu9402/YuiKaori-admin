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
REPO_DIR = HERE.parents[3]  # admin/catalog/tests/e2e → リポジトリの直下
EXPECTED_FILE = HERE.parent / "fixtures" / "expected" / "frontend.json"
PAGES = ["index.html", "songs.html", "tour.html", "my.html", "my_c.html", "my_f.html", "calendar.html", "event.html",
         "common.js", "common.css", "table-zoom.js", "site.js", "sub/setlist.html", "sub/search.html"]
PROBES = [("index", None), ("tour", None), ("checklist", "my.html"), ("checklist", "my_c.html"),
          ("checklist", "my_f.html"), ("calendar", None), ("event", None), ("sub", None)]


def chromium_path():
    return os.environ.get("CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser")


def build_site(dest, html_dir=REPO_DIR, json_dir=REPO_DIR):
    dest = Path(dest)
    for name in PAGES:
        src = Path(html_dir) / name
        if src.exists():
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest / name)
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
