"""作業用のコマンド（backup_db・export_json --check・record_verify・tasks）と、確認用サーバーのテスト。"""
import hashlib
import io
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from catalog import models as m
from catalog.exporter import write_all

from .helpers import LegacyDataTestCase

sys.path.insert(0, str(Path(settings.BASE_DIR) / "tools"))
import preview_server  # noqa: E402


def run(*args):
    # 実際にコマンドを実行したときと同じく、Django の起動時の検査（system checks）も通す
    out = io.StringIO()
    call_command(*args, stdout=out, skip_checks=False)
    return out.getvalue()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_db(path):
    with sqlite3.connect(path) as c:
        c.execute("create table t (x)")
        c.execute("insert into t values (1)")


class BackupDbTests(SimpleTestCase):
    def test_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "db.sqlite3"
            make_db(src)
            with mock.patch.dict(settings.DATABASES["default"], {"NAME": str(src)}):
                out = run("backup_db", "--label", "before-test", "--dir", str(Path(tmp) / "backup"))
            files = list((Path(tmp) / "backup").iterdir())
            self.assertEqual(len(files), 1)
            self.assertRegex(files[0].name, r"^db-\d{8}-\d{6}-before-test\.sqlite3$")
            self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
            with sqlite3.connect(files[0]) as c:
                self.assertEqual(c.execute("select x from t").fetchall(), [(1,)])
            self.assertIn("写しました", out)

    def test_bad_label(self):
        with self.assertRaises(CommandError):
            run("backup_db", "--label", "../x")


class ExportCheckTests(LegacyDataTestCase):
    def test_check_shows_changes_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_all(tmp)
            before = {p.name: sha(p) for p in Path(tmp).iterdir()}
            self.assertIn("変わるファイル: なし", run("export_json", "--site-dir", tmp, "--check"))

            live = m.Live.objects.order_by("pk").first()
            live.venue = "テスト会場"
            live.save()
            out = run("export_json", "--site-dir", tmp, "--check")
            self.assertIn("setlist.json:", out)
            self.assertIn(f"~ {live.pk} ", out)
            self.assertIn("変更 1", out)
            self.assertEqual({p.name: sha(p) for p in Path(tmp).iterdir()}, before)  # 書き出していない


class RecordVerifyTests(LegacyDataTestCase):
    def write_csv(self, tmp, text):
        path = Path(tmp) / "records.csv"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_dry_run_then_apply(self):
        live = m.Live.objects.order_by("pk").first()
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_csv(tmp, "live_id,status,date,source,note\n"
                                       f"{live.pk},一致,2026-11-24,https://example.com/a | 資料B,テストのメモ\n")
            out = run("record_verify", path)
            self.assertIn("1 件の公演が変わります", out)
            live.refresh_from_db()
            self.assertEqual(live.verify_status, "")  # --apply なしでは書き込まない

            run("record_verify", path, "--apply")
            live.refresh_from_db()
            self.assertEqual((live.verify_status, live.verify_date), ("ok", date(2026, 11, 24)))
            self.assertEqual(live.verify_source, "https://example.com/a\n資料B")
            self.assertEqual(live.verify_note, "テストのメモ")
            self.assertIn("変更なし", run("record_verify", path))

    def test_errors_write_nothing(self):
        first, second = m.Live.objects.order_by("pk")[:2]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_csv(tmp, f"live_id,status\n{first.pk},ok\n0000000000,ok\n{second.pk},たぶん\n")
            with self.assertRaises(CommandError):
                run("record_verify", path, "--apply")
        first.refresh_from_db()
        self.assertEqual(first.verify_status, "")


class TasksCommandTests(TestCase):
    def test_add_list_update_done(self):
        out = run("tasks", "add", "テストのタスク", "--category", "運用", "--priority", "高", "--detail", "最初のメモ")
        self.assertIn("テストのタスク", out)
        task = m.Task.objects.get(title="テストのタスク")
        self.assertEqual((task.category, task.priority, task.status), ("ops", 1, "todo"))

        run("tasks", "update", str(task.pk), "--status", "doing", "--note", "途中のメモ")
        task.refresh_from_db()
        self.assertEqual(task.status, "doing")
        self.assertIn("途中のメモ", task.detail)
        self.assertIn("テストのタスク", run("tasks", "list"))

        run("tasks", "done", str(task.pk), "--note", "終わった")
        task.refresh_from_db()
        self.assertEqual(task.status, "done")
        self.assertIn("【完了】", task.detail)
        self.assertNotIn("テストのタスク", run("tasks", "list"))
        self.assertIn("テストのタスク", run("tasks", "list", "--all"))

    def test_bad_values(self):
        with self.assertRaises(CommandError):
            run("tasks", "add", "x", "--status", "なにか")
        with self.assertRaises(CommandError):
            run("tasks", "done", "99999")


class PreviewServerTests(TestCase):
    def test_refuses_non_local_host(self):
        preview_server.check_host("127.0.0.1")
        for host in ["0.0.0.0", "192.168.1.10", "example.com"]:
            with self.subTest(host=host), self.assertRaises(SystemExit):
                preview_server.check_host(host)

    def test_copy_does_not_touch_source(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dest:
            make_db(Path(src) / "db.sqlite3")
            (Path(src) / "secret_key").write_text("本番の鍵")
            (Path(src) / "static").mkdir()
            before = {p.name: (sha(p) if p.is_file() else None) for p in Path(src).iterdir()}
            preview_server.copy_data(src, dest)
            self.assertEqual({p.name: (sha(p) if p.is_file() else None) for p in Path(src).iterdir()}, before)
            self.assertFalse((Path(dest) / "secret_key").exists())  # 本番の秘密鍵は写さない
            self.assertTrue((Path(dest) / "static").is_symlink())
            with sqlite3.connect(Path(dest) / "db.sqlite3") as c:
                self.assertEqual(c.execute("select x from t").fetchall(), [(1,)])

    def test_login_session(self):
        get_user_model().objects.create_superuser("owner", password="test-password-1234")
        key = preview_server.login_session()
        client = Client()
        client.cookies[settings.SESSION_COOKIE_NAME] = key
        self.assertEqual(client.get(reverse("admin:index")).status_code, 200)
