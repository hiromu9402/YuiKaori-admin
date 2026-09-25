import unicodedata

from django.test import SimpleTestCase

from catalog.normalize import clean, match_key, resolve

from .helpers import as_list, load_legacy


class CleanTests(SimpleTestCase):
    def test_nfc(self):
        # 「て」＋結合用濁点 → 「で」
        self.assertEqual(clean("半透明の世界で"), "半透明の世界で")

    def test_strip(self):
        self.assertEqual(clean("  Raise \n"), "Raise")
        self.assertEqual(clean(None), "")


class MatchKeyTests(SimpleTestCase):
    def test_variants_share_key(self):
        pairs = [
            ("Honey♥Come!!", "Honey♡Come!!"),
            ("Caramel Ribbon...", "Caramel Ribbon…"),
            ("CUE the Future　～「Q」のテーマ～", "CUE the Future 〜「Q」のテーマ〜"),
            ("CUE the Future　～「Q」のテーマ～", "CUE the Future ~「Q」のテーマ~"),
            ("Crispy love", "Crispy Love"),
            ("わざと触れた。", "わざと触れた"),
            ("Diorama-Drama", "Diorama Drama"),
            ("Shiny Blue", "Shiny blue"),
        ]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertEqual(match_key(a), match_key(b))

    def test_long_vowel_is_kept(self):
        self.assertNotEqual(match_key("ラブ"), match_key("ラーブ"))

    def test_no_collisions_between_existing_titles(self):
        """今のデータのすべての曲名（楽曲一覧とセットリスト）で、別の曲同士が同じキーにならないこと。"""
        titles = {s["title"] for s in load_legacy("song.json")}
        for live in load_legacy("setlist.json"):
            for key in ("setlist", "encore", "Wencore"):
                for item in as_list(live.get(key)):
                    titles.update(item["medley"] if isinstance(item, dict) else [item])
        titles = {unicodedata.normalize("NFC", t) for t in titles}
        seen = {}
        for t in sorted(titles):
            k = match_key(t)
            self.assertNotIn(k, seen, f"「{t}」と「{seen.get(k)}」が同じキーになります")
            seen[k] = t


class ResolveTests(SimpleTestCase):
    def setUp(self):
        self.raise_ = object()
        self.honey = object()
        self.by_title = {"Raise": self.raise_, "Honey♥Come!!": self.honey}
        self.aliases = {"レイズ": self.raise_}
        self.by_key = {match_key("Honey♥Come!!"): [self.honey], match_key("Raise"): [self.raise_]}

    def test_exact(self):
        self.assertEqual(resolve(" Raise ", self.by_title, self.aliases, self.by_key), (self.raise_, []))

    def test_alias(self):
        self.assertEqual(resolve("レイズ", self.by_title, self.aliases, self.by_key), (self.raise_, []))

    def test_candidates(self):
        self.assertEqual(resolve("Honey♡Come!!", self.by_title, self.aliases, self.by_key), (None, [self.honey]))

    def test_unknown(self):
        self.assertEqual(resolve("存在しない曲", self.by_title, self.aliases, self.by_key), (None, []))
