"""管理画面のテスト（Django test client）。"""
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

from catalog import models as m

from .helpers import LegacyDataTestCase

PASSWORD = "test-password-1234"


class AdminTestCase(LegacyDataTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = get_user_model().objects.create_superuser("owner", password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")


class AuthTests(LegacyDataTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        get_user_model().objects.create_superuser("owner", password=PASSWORD)

    def test_anonymous_is_redirected_to_login(self):
        for url in [reverse("admin:index"), reverse("admin:export"), reverse("admin:catalog_live_changelist"),
                    reverse("admin:catalog_live_setlist_text", args=["2025112401"])]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("admin:login"), response["Location"])

    def login(self, password):
        return self.client.post(reverse("admin:login"), {"username": "owner", "password": password},
                                REMOTE_ADDR="192.0.2.1", HTTP_USER_AGENT="test")

    def test_login(self):
        response = self.login(PASSWORD)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.login("wrong-password")
        # ロック中は正しいパスワードでもログインできない
        response = self.login(PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(get_user_model().objects.get(username="owner"),
                           backend="django.contrib.auth.backends.ModelBackend")
        url = reverse("admin:catalog_live_setlist_text", args=["2025112401"])
        self.assertEqual(client.post(url, {"text": "Raise"}).status_code, 403)
        self.assertEqual(client.post(reverse("admin:export")).status_code, 403)


class SmokeTests(AdminTestCase):
    def test_pages_render(self):
        pages = [reverse("admin:index"), reverse("admin:export")]
        for model, obj in [(m.Artist, m.Artist.objects.first()), (m.CD, m.CD.objects.first()),
                           (m.Song, m.Song.objects.first()), (m.SongAlias, None), (m.Tour, m.Tour.objects.first()),
                           (m.Live, m.Live.objects.first()), (m.Event, m.Event.objects.first()),
                           (m.ChecklistGroup, m.ChecklistGroup.objects.first()), (m.Task, None)]:
            name = model._meta.model_name
            pages += [reverse(f"admin:catalog_{name}_changelist"), reverse(f"admin:catalog_{name}_add"),
                      reverse(f"admin:catalog_{name}_changelist") + "?q=Raise"]
            if obj is not None:
                pages.append(reverse(f"admin:catalog_{name}_change", args=[obj.pk]))
        pages.append(reverse("admin:catalog_live_setlist_text", args=["2025112401"]))
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_setlist_text_is_prefilled(self):
        response = self.client.get(reverse("admin:catalog_live_setlist_text", args=["2025112402"]))
        self.assertContains(response, "[メドレー] LOVE涙色 / ラムのラブソング / Baby, Baby, Baby♡")

    def test_song_autocomplete(self):
        url = reverse("admin:autocomplete") + "?app_label=catalog&model_name=setlistitem&field_name=song&term=Honey"
        results = self.client.get(url).json()["results"]
        self.assertIn("Honey♥Come!!", [r["text"] for r in results])


class TaskTests(AdminTestCase):
    def test_list_edit_and_not_exported(self):
        from catalog.exporter import build_all
        task = m.Task.objects.create(title="テストのタスク", detail="メモの本文", category="ops")
        url = reverse("admin:catalog_task_changelist")
        self.assertContains(self.client.get(url + "?status__exact=todo"), "テストのタスク")
        self.assertContains(self.client.get(reverse("admin:catalog_task_change", args=[task.pk])), "メモの本文")
        self.assertNotIn("テストのタスク", json.dumps(build_all(), ensure_ascii=False))

    def test_done_tasks_are_hidden_by_default(self):
        m.Task.objects.create(title="まだのタスク", status="todo")
        m.Task.objects.create(title="終わったタスク", status="done")
        url = reverse("admin:catalog_task_changelist")
        cases = {
            "": (["まだのタスク"], ["終わったタスク"]),                  # 最初の表示は未完了だけ
            "?show=done": (["終わったタスク"], ["まだのタスク"]),
            "?show=all": (["まだのタスク", "終わったタスク"], []),
            "?status__exact=done": (["終わったタスク"], ["まだのタスク"]),  # 状態で選んだときはそちらに従う
            "?status__exact=todo": (["まだのタスク"], ["終わったタスク"]),
        }
        for query, (shown, hidden) in cases.items():
            with self.subTest(query=query):
                response = self.client.get(url + query)
                for title in shown:
                    self.assertContains(response, title)
                for title in hidden:
                    self.assertNotContains(response, title)
        self.assertContains(self.client.get(url), "未完了（最初の表示）")


class VerifyRecordTests(AdminTestCase):
    def test_edit_and_filter(self):
        live = m.Live.objects.get(id="2025112401")
        live.verify_status, live.verify_source = "ok", "https://example.com/setlist"
        live.save()
        url = reverse("admin:catalog_live_changelist")
        self.assertContains(self.client.get(url + "?verify_status__exact=ok"), "2025112401")
        self.assertNotContains(self.client.get(url + "?verify_status__exact=doubt"), "2025112401")
        self.assertContains(self.client.get(url + "?q=example.com"), "2025112401")

    def test_not_exported(self):
        from catalog.exporter import build_all
        live = m.Live.objects.get(id="2025112401")
        live.verify_status, live.verify_note = "fixed", "照合メモ"
        live.save()
        self.assertNotIn("照合メモ", json.dumps(build_all(), ensure_ascii=False))


class LiveAddTests(AdminTestCase):
    def add_live(self, **extra):
        data = {
            "id": "", "title": "テスト公演", "tour": "", "date": "2030-01-01", "venue": "テスト会場",
            "liveartist_set-TOTAL_FORMS": "1", "liveartist_set-INITIAL_FORMS": "0",
            "liveartist_set-0-artist": m.Artist.objects.get(name="小倉唯").pk, "liveartist_set-0-ord": "0",
            "setlist_items-TOTAL_FORMS": "0", "setlist_items-INITIAL_FORMS": "0",
            "checklist_entries-TOTAL_FORMS": "0", "checklist_entries-INITIAL_FORMS": "0",
        }
        data.update(extra)
        return self.client.post(reverse("admin:catalog_live_add"), data)

    def test_id_is_generated_and_redirects_to_setlist_input(self):
        response = self.add_live()
        live = m.Live.objects.get(title="テスト公演")
        self.assertEqual(live.id, "2030010101")
        self.assertRedirects(response, reverse("admin:catalog_live_setlist_text", args=[live.id]))
        # 日付がいちばん新しいので、書き出しの先頭に来る
        self.assertEqual(m.Live.objects.order_by("sort").first(), live)

    def test_create_event_checkbox(self):
        before = m.Event.objects.count()
        self.add_live(create_event="on")
        live = m.Live.objects.get(title="テスト公演")
        event = live.events.get()
        self.assertEqual(m.Event.objects.count(), before + 1)
        self.assertEqual((event.date, event.title, event.venue), (live.date, "テスト公演", "テスト会場"))
        self.assertEqual([a.name for a in event.artists.all()], ["小倉唯"])
        # 日付がいちばん新しいので、イベントも書き出しの先頭に来る
        self.assertEqual(m.Event.objects.order_by("sort").first(), event)

    def test_no_event_when_unchecked(self):
        before = m.Event.objects.count()
        self.add_live()
        self.assertEqual(m.Event.objects.count(), before)

    def test_checkbox_only_on_add_form(self):
        self.assertContains(self.client.get(reverse("admin:catalog_live_add")), 'name="create_event"')
        self.assertNotContains(self.client.get(reverse("admin:catalog_live_change", args=["2025112401"])),
                               'name="create_event"')

    def test_id_must_match_date(self):
        response = self.add_live(id="2030010201")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "公演IDの先頭8桁は開催日と同じにしてください")
        self.assertFalse(m.Live.objects.filter(title="テスト公演").exists())

    def test_create_event_action(self):
        live = m.Live.objects.get(id="2025112402")
        before = m.Event.objects.count()
        self.client.post(reverse("admin:catalog_live_changelist"),
                         {"action": "create_events", "_selected_action": [live.pk]})
        self.assertEqual(m.Event.objects.count(), before + 1)
        event = m.Event.objects.latest("id")
        self.assertEqual((event.date, event.title, event.live), (live.date, live.title, live))
        self.assertEqual([a.name for a in event.artists.all()], ["小倉唯"])


class SetlistInputTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.live = m.Live.objects.create(id="2030010101", title="テスト公演", date="2030-01-01")
        self.url = reverse("admin:catalog_live_setlist_text", args=[self.live.pk])

    def items(self):
        return [(i.section, i.pos, i.sub_pos, i.song.title)
                for i in self.live.setlist_items.select_related("song").order_by("section", "pos", "sub_pos")]

    def test_saves_known_titles(self):
        text = "Raise\n[メドレー] Honey♥Come!! / winter tale\n== アンコール\nBaby Sweet Berry Love"
        response = self.client.post(self.url, {"text": text})
        self.assertRedirects(response, reverse("admin:catalog_live_change", args=[self.live.pk]))
        self.assertEqual(self.items(), [
            ("encore", 1, 0, "Baby Sweet Berry Love"),
            ("main", 1, 0, "Raise"),
            ("main", 2, 1, "Honey♥Come!!"),
            ("main", 2, 2, "winter tale"),
        ])

    def test_replaces_existing_setlist(self):
        self.client.post(self.url, {"text": "Raise\nwinter tale"})
        self.client.post(self.url, {"text": "Raise"})
        self.assertEqual(self.items(), [("main", 1, 0, "Raise")])

    def test_syntax_error_is_shown(self):
        response = self.client.post(self.url, {"text": "Raise\n== おまけ\nwinter tale"})
        self.assertContains(response, "区分「おまけ」はわかりません")
        self.assertEqual(self.items(), [])

    def test_unknown_title_stops_with_candidates(self):
        response = self.client.post(self.url, {"text": "Raise\nHoney♡Come!!\n知らない曲"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "登録されていない曲名があります")
        honey = m.Song.objects.get(title="Honey♥Come!!")
        self.assertContains(response, f'value="alias:{honey.pk}"')
        self.assertEqual(self.items(), [])

    def test_resolve_with_alias_new_song_and_existing(self):
        honey = m.Song.objects.get(title="Honey♥Come!!")
        text = "Raise\nHoney♡Come!!\n知らない曲\nれいず"
        response = self.client.post(self.url, {
            "text": text, "step": "resolve",
            "title_0": "Honey♡Come!!", "choice_0": f"alias:{honey.pk}",
            "title_1": "知らない曲", "choice_1": "new",
            "title_2": "れいず", "choice_2": "existing", "target_2": "Raise",
        })
        self.assertRedirects(response, reverse("admin:catalog_live_change", args=[self.live.pk]))
        self.assertEqual([t for *_, t in self.items()], ["Raise", "Honey♥Come!!", "知らない曲", "Raise"])
        self.assertEqual(m.SongAlias.objects.get(alias="Honey♡Come!!").song, honey)
        self.assertEqual(m.SongAlias.objects.get(alias="れいず").song.title, "Raise")
        self.assertFalse(m.Song.objects.get(title="知らない曲").in_catalog)

    def test_resolve_requires_choice(self):
        response = self.client.post(self.url, {"text": "知らない曲", "step": "resolve", "title_0": "知らない曲"})
        self.assertContains(response, "「知らない曲」の扱いを選んでください")
        self.assertFalse(m.Song.objects.filter(title="知らない曲").exists())


class ExportViewTests(AdminTestCase):
    def test_export_writes_to_site_dir(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(SITE_DIR=Path(tmp)):
            response = self.client.post(reverse("admin:export"), follow=True)
            self.assertContains(response, "書き出しました")
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),
                             ["CD.json", "checklist.json", "event.json", "setlist.json", "song.json", "tours.json"])
            self.assertEqual(len(json.loads((Path(tmp) / "song.json").read_text(encoding="utf-8"))), 187)
            response = self.client.post(reverse("admin:export"), follow=True)
            self.assertContains(response, "変更はありませんでした")

    def test_export_refuses_when_invalid(self):
        m.Live.objects.create(id="2030010101", title="セットリストなし", date="2030-01-01")
        with tempfile.TemporaryDirectory() as tmp, override_settings(SITE_DIR=Path(tmp)):
            response = self.client.post(reverse("admin:export"), follow=True)
            self.assertContains(response, "書き出しませんでした")
            self.assertContains(response, "本編のセットリストが空です")
            self.assertEqual(list(Path(tmp).iterdir()), [])
