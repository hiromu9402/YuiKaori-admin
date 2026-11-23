"""公開ページの回帰テスト（headless Chromium）。

正解データを取り込んだ DB から JSON を書き出し、今の HTML/JS と組み合わせて表示結果を取り出す。
その結果が、DB 化する前の画面の結果（fixtures/expected/frontend.json）と一致することを確かめる。
Chromium がない環境では skip する。
"""
import copy
import json
import tempfile
import unittest

from django.test import tag

from catalog.exporter import write_all

from .e2e import runner
from .helpers import LegacyDataTestCase


@tag("e2e")
@unittest.skipUnless(runner.chromium_path(), "Chromium がないので画面のテストを飛ばします")
@unittest.skipUnless((runner.SITE_DIR / "index.html").exists(),
                     f"公開サイトのリポジトリ（{runner.SITE_DIR}）がないので画面のテストを飛ばします")
class FrontendRegressionTests(LegacyDataTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with tempfile.TemporaryDirectory() as json_dir, tempfile.TemporaryDirectory() as site_dir:
            write_all(json_dir)
            runner.build_site(site_dir, json_dir=json_dir)
            cls.actual = runner.collect(site_dir)
        cls.expected = json.loads(runner.EXPECTED_FILE.read_text(encoding="utf-8"))
        # DB 化で意図して変わる点：月がゼロ埋め（"03"）されていたイベントが、カレンダーに出るようになる
        cls.expected = copy.deepcopy(cls.expected)
        cls.expected["calendar"]["events"] += 1

    def test_index_counts(self):
        self.assertEqual(self.actual["index"], self.expected["index"])

    def test_tour_options_and_tables(self):
        self.assertEqual(self.actual["tour"], self.expected["tour"])

    def test_checklists(self):
        for page in ("my.html", "my_c.html", "my_f.html"):
            with self.subTest(page=page):
                expected = self.expected[page]
                # 旧版の my_c.html にあった存在しない公演ID（取り込みで除外している）
                expected["items"] = [i for i in expected["items"] if i["id"] != "2020120501"]
                expected["missing"].pop("2020120501", None)
                self.assertEqual(self.actual[page]["items"], expected["items"])
                self.assertEqual(self.actual[page]["missing"], expected["missing"])

    def test_calendar_and_event(self):
        self.assertEqual(self.actual["calendar"], self.expected["calendar"])
        self.assertEqual(self.actual["event"], self.expected["event"])
        self.assertEqual(self.actual["event"]["absoluteLinks"], 0)

    def test_sub_pages(self):
        self.assertEqual(self.actual["sub"], self.expected["sub"])
