"""公開前のプレビュー（管理画面の /preview/。ログインが必要）。

公開サイトのリポジトリ（settings.SITE_DIR）の HTML・CSS・JS と、DB の今の内容からその場で作った JSON で、
公開サイトと同じページを表示する。書き出しや push の前に、DB を直した結果を確かめるためのもの。
- 出すファイルは、公開サイトと同じ許可リスト（直下の .html/.css/.js/.json と sub/ の .html）だけ
- 各ページの上に「プレビュー（未公開）」の帯を出し、フッターの「データ更新」は「未公開」にする
"""
import json
import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.html import escape

from . import exporter

# 公開サイトの許可リスト（公開サイトのリポジトリの tools/site_files.py と同じ）
ALLOWED = [
    re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(html|css|js|json)$"),
    re.compile(r"^sub/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.html$"),
]
# DB から作る JSON
DATA = {
    "song.json": exporter.export_songs,
    "CD.json": exporter.export_cds,
    "setlist.json": exporter.export_lives,
    "event.json": exporter.export_events,
    "tours.json": exporter.export_tours,
    "checklist.json": exporter.export_checklist,
}

BANNER = """
<div id="yk-preview-banner" style="position:sticky;top:0;z-index:9999;background:#b45309;color:#fff;
  font:600 13px/1.6 system-ui,sans-serif;padding:6px 12px;text-align:center">
  プレビュー（未公開）：管理画面の DB の今の内容で表示しています。
  <a href="{admin}" style="color:#fff;text-decoration:underline">管理画面に戻る</a>
</div>"""
FOOTER_SCRIPT = """
<script>
// フッターの「データ更新」を「未公開」にする（site.js があとから書き換えても戻す）
(function () {
  const mark = () => {
    const s = document.querySelector('.site-footer .updated');
    if (s && s.textContent !== '未公開（プレビュー）') s.textContent = '未公開（プレビュー）';
    return s;
  };
  const watch = () => {
    const s = mark();
    if (!s) return setTimeout(watch, 100);
    new MutationObserver(mark).observe(s, { childList: true, characterData: true, subtree: true });
  };
  watch();
})();
</script>"""


def allowed(relpath):
    return any(p.match(relpath) for p in ALLOWED)


def no_store(response):
    response["Cache-Control"] = "no-store"
    return response


def render_page(path, text, admin_url):
    """HTML に、プレビューの帯と、フッターの書き換えを入れる。"""
    banner = BANNER.format(admin=escape(admin_url))
    text, n = re.subn(r"(<body[^>]*>)", lambda m: m.group(1) + banner, text, count=1)
    if not n:
        text = banner + text
    if "</body>" in text:
        text = text.replace("</body>", FOOTER_SCRIPT + "</body>", 1)
    else:
        text += FOOTER_SCRIPT
    return text


def serve(request, path, admin_url):
    path = path or "index.html"
    if path == "meta.json":
        # 公開するときに作るファイル。プレビューでは日付を持たせない（フッターは「未公開」にする）
        return no_store(HttpResponse(json.dumps({"data_updated": None}), content_type="application/json"))
    if not allowed(path):
        raise Http404
    if path in DATA:
        body = json.dumps(DATA[path](), ensure_ascii=False)
        return no_store(HttpResponse(body, content_type="application/json; charset=utf-8"))
    site_dir = Path(settings.SITE_DIR).resolve()
    file = (site_dir / path).resolve()
    if site_dir not in file.parents or not file.is_file():
        raise Http404
    if path.endswith(".html"):
        text = render_page(path, file.read_text(encoding="utf-8"), admin_url)
        return no_store(HttpResponse(text, content_type="text/html; charset=utf-8"))
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if content_type.startswith("text/") or content_type in ("application/javascript", "text/javascript"):
        content_type += "; charset=utf-8"
    return no_store(HttpResponse(file.read_bytes(), content_type=content_type))
