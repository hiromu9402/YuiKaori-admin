"""公開の仕組みのテスト（GitHub Pages に載せるファイル、リバースプロキシのパスの下で動かす設定）。"""
import importlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.wsgi import get_wsgi_application
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.prefix import PrefixMiddleware

DEPLOY_DIR = Path(settings.BASE_DIR) / "deploy"
sys.path.insert(0, str(DEPLOY_DIR))
build_site = importlib.import_module("build_site")
site_files = importlib.import_module("site_files")

PASSWORD = "test-password-1234"


class BuildSiteTests(SimpleTestCase):
    def test_only_public_files_are_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = build_site.build(Path(tmp) / "_site")
            out = sorted(p.relative_to(Path(tmp) / "_site").as_posix()
                         for p in (Path(tmp) / "_site").rglob("*") if p.is_file())
        self.assertEqual(out, files)
        for page in ["index.html", "songs.html", "tour.html", "event.html", "calendar.html", "my.html",
                     "sub/setlist.html", "sub/search.html", "common.css", "site.js", "setlist.json"]:
            with self.subTest(page=page):
                self.assertIn(page, files)
        for path in files:
            with self.subTest(path=path):
                self.assertFalse(path.startswith(("admin/", ".git", ".github/", "_site/")))
                self.assertNotIn(path, ["README.md", "HANDOFF.md", ".gitignore"])

    def test_allowlist(self):
        for path in ["index.html", "song.json", "sub/setlist.html"]:
            with self.subTest(path=path):
                self.assertTrue(site_files.allowed(path))
        for path in ["HANDOFF.md", "README.md", ".gitignore", ".git/config", "admin/serve.py",
                     "admin/config/settings.py", ".github/workflows/pages.yml", "sub/../admin/x.html",
                     "sub/notes.md", "../index.html", ".hidden.html"]:
            with self.subTest(path=path):
                self.assertFalse(site_files.allowed(path))

    def test_refuses_non_empty_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "old.txt").write_text("x")
            with self.assertRaises(SystemExit):
                build_site.build(tmp)


class PrefixMiddlewareTests(SimpleTestCase):
    def call(self, path):
        seen = {}

        def app(environ, start_response):
            seen.update(script=environ["SCRIPT_NAME"], path=environ["PATH_INFO"])
            return []

        PrefixMiddleware(app, "/example")({"PATH_INFO": path}, None)
        return seen["script"], seen["path"]

    def test_path_with_or_without_prefix(self):
        # プロキシがパスを付けたまま転送しても、外して転送しても同じになる
        self.assertEqual(self.call("/example/login/"), ("/example", "/login/"))
        self.assertEqual(self.call("/login/"), ("/example", "/login/"))
        self.assertEqual(self.call("/example"), ("/example", "/"))
        self.assertEqual(self.call("/"), ("/example", "/"))
        # 名前が前方一致するだけの別のパスは外さない
        self.assertEqual(self.call("/example2/"), ("/example", "/example2/"))


PREFIX_SETTINGS = {"SESSION_COOKIE_PATH": "/example/", "CSRF_COOKIE_PATH": "/example/",
                   "STATIC_URL": "/example/static/"}


class PrefixSettingsTests(SimpleTestCase):
    """YUIKAORI_URL_PREFIX から作られる設定を、別のプロセスで settings を読み込んで確かめる。"""

    def load(self, prefix):
        env = {**os.environ, "YUIKAORI_URL_PREFIX": prefix, "DJANGO_SETTINGS_MODULE": "config.settings"}
        code = ("from django.conf import settings as s; import json; "
                "print(json.dumps({k: getattr(s, k) for k in %r}))" % sorted(PREFIX_SETTINGS))
        out = subprocess.run([sys.executable, "-c", code], cwd=settings.BASE_DIR, env=env,
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_with_prefix(self):
        for prefix in ["/example", "example/", "/example/"]:
            with self.subTest(prefix=prefix):
                self.assertEqual(self.load(prefix), PREFIX_SETTINGS)

    def test_without_prefix(self):
        self.assertEqual(self.load(""), {"SESSION_COOKIE_PATH": "/", "CSRF_COOKIE_PATH": "/", "STATIC_URL": "/static/"})


@override_settings(**PREFIX_SETTINGS)
class UnderPrefixTests(TestCase):
    """リバースプロキシの /example の下で動かしたときの動き。本番と同じ WSGI の経路（PrefixMiddleware）で確かめる。"""

    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.create_superuser("owner", password=PASSWORD)

    def request(self, path, method="GET", body=b"", cookies=""):
        app = PrefixMiddleware(get_wsgi_application(), "/example")
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "", "HTTP_HOST": "127.0.0.1",
                   "HTTP_COOKIE": cookies, "CONTENT_TYPE": "application/x-www-form-urlencoded",
                   "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        if "?" in path:
            environ["PATH_INFO"], environ["QUERY_STRING"] = path.split("?", 1)
        setup_testing_defaults(environ)
        result = {}

        def start_response(status, headers, exc_info=None):
            result.update(status=int(status.split()[0]), headers=headers)

        result["body"] = b"".join(app(environ, start_response)).decode()
        return result

    def header(self, result, name):
        return [v for k, v in result["headers"] if k.lower() == name.lower()]

    def test_redirects_and_links_have_prefix(self):
        # プロキシがパスを付けたまま転送しても、外して転送しても同じになる
        for path in ["/example/", "/"]:
            with self.subTest(path=path):
                response = self.request(path)
                self.assertEqual(response["status"], 302)
                self.assertEqual(self.header(response, "Location"), ["/example/login/?next=/example/"])
        login = self.request("/example/login/")
        self.assertEqual(login["status"], 200)
        self.assertIn('action="/example/login/', login["body"])
        self.assertIn("/example/static/admin/css/", login["body"])

    def test_login_and_cookies_are_scoped_to_the_admin(self):
        login = self.request("/example/login/")
        cookies = self.header(login, "Set-Cookie")
        self.assertTrue(cookies)
        for cookie in cookies:
            with self.subTest(cookie=cookie):
                self.assertTrue(cookie.startswith("yuikaori_"))
                self.assertIn("Path=/example/", cookie)
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login["body"]).group(1)
        csrf_cookie = cookies[0].split(";")[0]
        body = urlencode({"username": "owner", "password": PASSWORD, "csrfmiddlewaretoken": token,
                          "next": "/example/"}).encode()
        response = self.request("/example/login/", "POST", body, csrf_cookie)
        self.assertEqual(response["status"], 302)
        self.assertEqual(self.header(response, "Location"), ["/example/"])
        session = [c for c in self.header(response, "Set-Cookie") if c.startswith("yuikaori_sessionid=")]
        self.assertEqual(len(session), 1)
        self.assertIn("Path=/example/", session[0])
        self.assertIn("HttpOnly", session[0])


class LoginRequiredEverywhereTests(TestCase):
    """インターネットから開けるので、ログイン画面以外はどのページもログインが必要なことを確かめる。"""

    def test_every_model_page_requires_login(self):
        urls = [reverse("admin:index"), reverse("admin:export"), reverse("admin:password_change")]
        for model in admin.site._registry:
            info = (model._meta.app_label, model._meta.model_name)
            urls += [reverse("admin:%s_%s_changelist" % info), reverse("admin:%s_%s_add" % info),
                     reverse("admin:%s_%s_change" % info, args=[1])]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("admin:login")))
