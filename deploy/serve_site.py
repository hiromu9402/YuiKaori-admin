"""公開サイトを配信する小さなサーバー（許可リスト方式）。

許可リスト（site_files.py。GitHub Pages に載せる内容と同じ）に合うファイルだけを返し、それ以外は 404 にする。
.git/、admin/（管理画面のソースやデータ）、HANDOFF.md などの作業用ファイルは外から見えない。

    python3 admin/deploy/serve_site.py            # 127.0.0.1:8765 で待ち受ける
    python3 admin/deploy/serve_site.py --port 8766
"""
import argparse
import http.server
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_files import SITE_DIR, allowed  # noqa: E402  許可リストは build_site.py と共通


class SiteHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def send_head(self):
        path = unquote(urlsplit(self.path).path).lstrip("/")
        if path == "":
            path = "index.html"
        if not allowed(path) or not (SITE_DIR / path).is_file():
            self.send_error(404, "Not Found")
            return None
        return super().send_head()

    def end_headers(self):
        # 更新した内容がすぐ見えるように、毎回サーバーに確認させる（変わっていなければ 304 が返る）
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with http.server.ThreadingHTTPServer((args.host, args.port), SiteHandler) as server:
        print(f"公開サイトを http://{args.host}:{args.port}/ で配信します（{SITE_DIR}）", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
