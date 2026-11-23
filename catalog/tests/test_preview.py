"""公開前のプレビュー（/preview/）と、公開中との違いのまとめのテスト。"""
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from catalog import exporter
from catalog import models as m
from catalog.exporter import write_all

from .helpers import LegacyDataTestCase

PASSWORD = "test-password-1234"


class PreviewTests(LegacyDataTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = get_user_model().objects.create_superuser("owner", password=PASSWORD)

    def setUp(self):
        # 公開サイトのリポジトリの代わり（公開するファイルと、公開しないファイル）
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        site = Path(self._tmp.name)
        (site / "sub").mkdir()
        (site / ".git").mkdir()
        (site / "index.html").write_text('<html><body class="home"><p>トップ</p><script src="site.js"></script></body></html>')
        (site / "sub" / "setlist.html").write_text("<html><body><p>セットリスト</p></body></html>")
        (site / "common.css").write_text("body { color: red; }")
        (site / "site.js").write_text("console.log('site');")
        (site / "README.md").write_text("公開しない")
        (site / ".git" / "config").write_text("[core]")
        (site / "song.json").write_text("[]")  # 古い公開ファイル（プレビューでは使わない）
        self.site = site
        override = override_settings(SITE_DIR=site)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def url(self, path=""):
        return reverse("admin:preview", args=[path])

    def test_login_required(self):
        self.client.logout()
        for path in ["", "index.html", "song.json", "common.css"]:
            with self.subTest(path=path):
                response = self.client.get(self.url(path))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("admin:login"), response["Location"])

    def test_pages_have_banner_and_footer_override(self):
        for path in ["", "index.html", "sub/setlist.html"]:
            with self.subTest(path=path):
                response = self.client.get(self.url(path))
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response["Cache-Control"])  # ブラウザに残さない
                text = response.content.decode()
                self.assertIn("プレビュー（未公開）", text)
                self.assertIn(f'href="{reverse("admin:index")}"', text)
                self.assertIn("未公開（プレビュー）", text)
        text = self.client.get(self.url("index.html")).content.decode()
        self.assertLess(text.index('<body class="home">'), text.index("プレビュー（未公開）"))
        self.assertLess(text.index("未公開（プレビュー）"), text.index("</body>"))

    def test_data_comes_from_db(self):
        response = self.client.get(self.url("song.json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), exporter.export_songs())
        self.assertGreater(len(json.loads(response.content)), 0)  # 古い公開ファイル（[]）ではない
        for name in ["CD.json", "setlist.json", "event.json", "tours.json", "checklist.json"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(self.url(name)).status_code, 200)
        self.assertEqual(json.loads(self.client.get(self.url("meta.json")).content), {"data_updated": None})

    def test_static_files_and_allowlist(self):
        self.assertEqual(self.client.get(self.url("common.css")).content, b"body { color: red; }")
        self.assertTrue(self.client.get(self.url("site.js"))["Content-Type"].endswith("javascript; charset=utf-8"))
        for path in ["README.md", ".git/config", "missing.html", "../secret.html", "sub/../README.md",
                     "admin/serve.py", "sub/notes.md"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(self.url(path)).status_code, 404)

    def test_changes_on_top_and_export_pages(self):
        write_all(self.site)
        top = self.client.get(reverse("admin:index"))
        self.assertContains(top, "公開前のプレビューを開く")
        self.assertContains(top, "公開中のサイトとの違い：ありません")

        live = m.Live.objects.order_by("pk").first()
        live.venue = "テスト会場"
        live.save()
        for url in [reverse("admin:index"), reverse("admin:export")]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "公開中のサイトとの違い（setlist.json")
                self.assertContains(response, f"~ {live.pk} ")
