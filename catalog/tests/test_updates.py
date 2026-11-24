"""データ更新の候補（check_updates）のテスト。外部のサイトにはアクセスせず、架空のサイトのページを差し替える。"""
import importlib.metadata
import io
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog import models as m
from catalog import updates

TODAY = date(2026, 11, 24)

# 架空のイベント一覧のサイト（https://events.example.com）の設定
SOURCE = {
    "name": "テストの一覧",
    "list_url": "https://events.example.com/people/{actor_id}/events?page={page}",
    "event_url": "https://events.example.com/events/{id}",
    "actors": {"小倉唯": 1, "石原夏織": 2, "ゆいかおり": 3},
    "patterns": {
        "item": r'<div class="item">',
        "date": r'<time>(\d{4})-(\d{2})-(\d{2})</time>',
        "link": r'<a class="ev" href="/events/(\d+)">(.*?)</a>',
        "venue": r'<span class="venue">(.*?)</span>',
        "actor": r'<span class="who">(.*?)</span>',
    },
}


def page(*events):
    items = "".join(f'<div class="item"><time>{d}</time><a class="ev" href="/events/{eid}">{title}</a>'
                    f'<span class="venue">{venue}</span><span class="who">小倉唯</span></div>'
                    for eid, d, title, venue in events)
    return f"<html><body>{items}</body></html>"


class NoNetworkMixin:
    def setUp(self):
        super().setUp()

        def no_network(*args, **kwargs):
            raise AssertionError("テストの中で外にアクセスしようとしました")
        patcher = mock.patch("urllib.request.urlopen", no_network)
        patcher.start()
        self.addCleanup(patcher.stop)
        # PyPI も読まない。既定では、どのパッケージも今の版が最新とする
        patcher = mock.patch.object(updates, "fetch_json", pypi())
        patcher.start()
        self.addCleanup(patcher.stop)


def pypi(latest=None, vulns=None):
    """架空の PyPI。latest に {名前: 新しい版}、vulns に {名前: [脆弱性の ID]} を渡す。"""
    latest, vulns = latest or {}, vulns or {}

    def fetch(url):
        parts = url.split("/pypi/")[1].rstrip("/").split("/")
        name = parts[0]
        if parts[1:] == ["json"]:
            version = latest.get(name) or importlib.metadata.version(name)
            return {"info": {"version": version}, "urls": [{"upload_time": "2026-11-03T12:00:00"}]}
        return {"info": {"version": parts[1]}, "vulnerabilities": [{"id": v} for v in vulns.get(name, [])]}
    return fetch


class ParseTests(TestCase):
    def test_parse_events(self):
        events = updates.parse_events(page((1, "2027-02-07", "小倉 唯 LIVE 2027 &amp; テスト", "記念講堂")), SOURCE["patterns"])
        self.assertEqual(events, [{"id": "1", "date": "2027-02-07", "title": "小倉 唯 LIVE 2027 & テスト",
                                   "venue": "記念講堂", "actors": ["小倉唯"]}])

    def test_same_event(self):
        self.assertTrue(updates.same_event("小倉 唯 LIVE 2027「すーぱー」", "小倉唯 LIVE 2027 『すーぱー』"))
        self.assertTrue(updates.same_event("YUI OGURA SYMPHONIC CONCERT 2026 1部", "YUI OGURA SYMPHONIC CONCERT 2026 Once Upon a Melody 1部"))
        self.assertFalse(updates.same_event("ウマ娘 7th EVENT", "小倉 唯 お渡し会"))


class FetchTests(NoNetworkMixin, TestCase):
    def test_stops_at_lookback_and_dedupes(self):
        urls = []
        pages = {
            1: page((10, "2027-01-01", "新しいイベント", "会場A"), (11, "2026-11-01", "最近のイベント", "会場B")),
            2: page((12, "2026-08-01", "古いイベント", "会場C")),  # LOOKBACK_DAYS より前
            3: page((13, "2026-01-01", "読まないページ", "会場D")),
        }

        def fetch(url):
            urls.append(url)
            return pages[int(url.rsplit("=", 1)[1])]

        found, errors = updates.fetch_recent(SOURCE, TODAY, fetch=fetch, wait=0)
        self.assertEqual([e["id"] for e in found], ["11", "10"])  # 3 人で同じイベントでも 1 件
        self.assertEqual(errors, [])
        self.assertIn("https://events.example.com/people/1/events?page=1", urls)
        self.assertFalse(any(u.endswith("page=3") for u in urls))  # 古いイベントが出たページで止まる

    def test_fetch_error_is_recorded(self):
        def fetch(url):
            raise OSError("つながらない")
        found, errors = updates.fetch_recent(SOURCE, TODAY, fetch=fetch, wait=0)
        self.assertEqual(found, [])
        self.assertEqual(len(errors), len(SOURCE["actors"]))


class ReportTests(NoNetworkMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        yui = m.Artist.objects.create(name="小倉唯")
        live = m.Live.objects.create(id="2026110101", title="登録済みの公演", date=date(2026, 11, 1))

        def event(d, title, class1, live=None):
            ev = m.Event.objects.create(date=d, title=title, class1=class1, live=live)
            m.EventArtist.objects.create(event=ev, artist=yui)
            return ev
        event(date(2027, 1, 1), "既に登録済みのイベント", "イベント")
        cls.no_setlist = event(date(2026, 10, 1), "セットリストのないライブ", "ライブ")
        event(date(2026, 11, 1), "セットリストのあるライブ", "ライブ", live)
        event(date(2024, 1, 1), "古いライブ", "ライブ")  # SETLIST_DAYS より前
        cls.upcoming = event(date(2026, 12, 10), "これからのライブ", "ライブ")
        event(date(2026, 12, 11), "これからの雑誌", "雑誌")

    def fetch(self, url):
        return page((1, "2027-01-01", "既に登録済みのイベント！", "会場"), (2, "2027-01-01", "まだ登録していないイベント", "会場"))

    def test_build_report(self):
        report = updates.build_report(TODAY, fetch=self.fetch, wait=0, source=SOURCE)
        self.assertEqual([e["title"] for e in report["new_events"]], ["まだ登録していないイベント"])
        self.assertEqual(report["new_events"][0]["url"], "https://events.example.com/events/2")
        self.assertEqual([e["pk"] for e in report["missing_setlists"]], [self.no_setlist.pk])
        self.assertEqual([e["pk"] for e in report["upcoming"]], [self.upcoming.pk])
        text = updates.summary(report, "https://admin.example.com/")
        self.assertIn("テストの一覧にあって DB にないイベント: 1 件", text)
        self.assertIn("https://admin.example.com/", text)

    def test_without_source(self):
        # 読み先の設定がないときは、外のサイトを読まず、ほかの 2 つだけを集める
        with tempfile.TemporaryDirectory() as tmp, override_settings(DATA_DIR=Path(tmp)):
            report = updates.build_report(TODAY, fetch=self.fetch, wait=0)
        self.assertFalse(report["source_enabled"])
        self.assertEqual(report["new_events"], [])
        self.assertEqual(len(report["missing_setlists"]), 1)
        self.assertNotIn("DB にないイベント", updates.summary(report))

    def test_command_saves_notifies_and_shows_on_top(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(DATA_DIR=Path(tmp)), \
                mock.patch.object(updates, "fetch_page", self.fetch), mock.patch.object(updates, "WAIT_SECONDS", 0), \
                mock.patch.object(updates, "today", lambda: TODAY), mock.patch("subprocess.run") as run:
            (Path(tmp) / "update_sources.json").write_text(json.dumps(SOURCE, ensure_ascii=False), encoding="utf-8")
            run.return_value.returncode = 0
            call_command("check_updates", "--notify", stdout=io.StringIO())
            sent = run.call_args.args[0][1]
            self.assertIn("ゆいかおりDB の更新の候補（2026-11-24）", sent)
            saved = json.loads((Path(tmp) / "update_report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["new_events"]), 1)

            user = get_user_model().objects.create_superuser("owner", password="test-password-1234")
            self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
            response = self.client.get(reverse("admin:index"))
            self.assertContains(response, "テストの一覧にあって DB にないイベント")
            self.assertContains(response, "まだ登録していないイベント")
            self.assertContains(response, reverse("admin:catalog_event_change", args=[self.no_setlist.pk]))

    def test_notify_new_only_when_increased(self):
        pages = {"html": page((2, "2027-01-01", "まだ登録していないイベント", "会場"))}
        with tempfile.TemporaryDirectory() as tmp, override_settings(DATA_DIR=Path(tmp)), \
                mock.patch.object(updates, "fetch_page", lambda url: pages["html"]), \
                mock.patch.object(updates, "WAIT_SECONDS", 0), \
                mock.patch.object(updates, "today", lambda: TODAY), mock.patch("subprocess.run") as run:
            (Path(tmp) / "update_sources.json").write_text(json.dumps(SOURCE, ensure_ascii=False), encoding="utf-8")
            run.return_value.returncode = 0
            # 1 回目：前回がないので、すべて新しい → 送る
            call_command("check_updates", "--notify-new", stdout=io.StringIO())
            self.assertEqual(run.call_count, 1)
            self.assertIn("候補が増えました", run.call_args.args[0][1])
            # 2 回目：同じ候補 → 送らない（保存はする）
            out = io.StringIO()
            call_command("check_updates", "--notify-new", stdout=out)
            self.assertEqual(run.call_count, 1)
            self.assertIn("新しい候補がないので", out.getvalue())
            saved = json.loads((Path(tmp) / "update_report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["new_count"], 0)
            # 3 回目：新しいイベントが増えた → 増えた分だけを送る
            pages["html"] = page((2, "2027-01-01", "まだ登録していないイベント", "会場"),
                                 (3, "2027-02-02", "新しく発表されたイベント", "会場"))
            call_command("check_updates", "--notify-new", stdout=io.StringIO())
            self.assertEqual(run.call_count, 2)
            sent = run.call_args.args[0][1]
            self.assertIn("テストの一覧にあって DB にないイベント: 1 件", sent)
            self.assertIn("新しく発表されたイベント", sent)
            self.assertNotIn("まだ登録していないイベント", sent)
            # 管理画面のトップでは、増えたものに「新」の印が付く
            user = get_user_model().objects.create_superuser("owner", password="test-password-1234")
            self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
            self.assertContains(self.client.get(reverse("admin:index")), "は前回から増えたものです（1 件）")

    def test_top_page_before_first_run(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(DATA_DIR=Path(tmp)):
            user = get_user_model().objects.create_superuser("owner", password="test-password-1234")
            self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
            self.assertContains(self.client.get(reverse("admin:index")), "まだ集めていません")

    def test_dry_run_saves_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(DATA_DIR=Path(tmp)), \
                mock.patch.object(updates, "fetch_page", self.fetch), mock.patch.object(updates, "WAIT_SECONDS", 0), \
                mock.patch.object(updates, "today", lambda: TODAY), mock.patch("subprocess.run") as run:
            (Path(tmp) / "update_sources.json").write_text(json.dumps(SOURCE, ensure_ascii=False), encoding="utf-8")
            call_command("check_updates", "--dry-run", "--notify", stdout=io.StringIO())
            self.assertFalse((Path(tmp) / "update_report.json").exists())
            run.assert_not_called()


class PackageTests(NoNetworkMixin, TestCase):
    def test_outdated_packages(self):
        found, errors = updates.outdated_packages(pypi({"django": "99.0"}, {"django": ["PYSEC-0000-1"]}))
        self.assertEqual(errors, [])
        self.assertEqual([(p["name"], p["latest"], p["vulnerabilities"]) for p in found],
                         [("django", "99.0", ["PYSEC-0000-1"])])
        self.assertEqual(found[0]["date"], "2026-11-03")
        self.assertIn("今の版の脆弱性: PYSEC-0000-1", found[0]["title"])

    def test_up_to_date_and_errors(self):
        self.assertEqual(updates.outdated_packages(pypi()), ([], []))

        def broken(url):
            raise OSError("つながりません")
        found, errors = updates.outdated_packages(broken)
        self.assertEqual(found, [])
        self.assertEqual(len(errors), len(updates.requirements()))

    def test_notify_and_top_page(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(DATA_DIR=Path(tmp)), \
                mock.patch.object(updates, "today", lambda: TODAY), mock.patch("subprocess.run") as run:
            run.return_value.returncode = 0
            with mock.patch.object(updates, "fetch_json", pypi({"django": "99.0"})):
                call_command("check_updates", "--notify-new", stdout=io.StringIO())
            sent = run.call_args.args[0][1]
            self.assertIn("新しい版が出たパッケージ（管理画面）: 1 件", sent)
            self.assertIn("django", sent)
            # 同じ版のままなら知らせない。さらに新しい版が出たら、また知らせる
            with mock.patch.object(updates, "fetch_json", pypi({"django": "99.0"})):
                call_command("check_updates", "--notify-new", stdout=io.StringIO())
            self.assertEqual(run.call_count, 1)
            with mock.patch.object(updates, "fetch_json", pypi({"django": "99.1"})):
                call_command("check_updates", "--notify-new", stdout=io.StringIO())
            self.assertEqual(run.call_count, 2)
            self.assertIn("99.1", run.call_args.args[0][1])

            user = get_user_model().objects.create_superuser("owner", password="test-password-1234")
            self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
            response = self.client.get(reverse("admin:index"))
            self.assertContains(response, "新しい版が出たパッケージ（1 件")
            self.assertContains(response, "https://pypi.org/project/django/99.1/")
