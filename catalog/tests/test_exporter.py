import datetime

from django.test import SimpleTestCase

from catalog import models as m
from catalog.exporter import ja_date, one_or_many, setlist_sections


class FormatTests(SimpleTestCase):
    def test_ja_date_has_no_zero_padding(self):
        self.assertEqual(ja_date(datetime.date(2025, 3, 7)), "2025年3月7日")
        self.assertEqual(ja_date(datetime.date(2025, 11, 24)), "2025年11月24日")

    def test_one_or_many(self):
        self.assertEqual(one_or_many([]), "")
        self.assertEqual(one_or_many(["小倉唯"]), "小倉唯")
        self.assertEqual(one_or_many(["小倉唯", "石原夏織"]), ["小倉唯", "石原夏織"])

    def test_split_multi(self):
        self.assertEqual(m.split_multi("小倉唯 / 塚田耕平"), ["小倉唯", "塚田耕平"])
        self.assertEqual(m.split_multi("藤末樹・齊藤湧太"), ["藤末樹・齊藤湧太"])
        self.assertEqual(m.split_multi(""), [])


class SetlistSectionsTests(SimpleTestCase):
    def item(self, section, pos, sub_pos, title):
        return m.SetlistItem(section=section, pos=pos, sub_pos=sub_pos, song=m.Song(title=title))

    def test_medley_and_sections(self):
        items = [
            self.item("encore", 1, 0, "E1"),
            self.item("main", 2, 2, "M2"),
            self.item("main", 1, 0, "A"),
            self.item("main", 2, 1, "M1"),
            self.item("main", 3, 0, "B"),
            self.item("wencore", 1, 0, "W1"),
        ]
        out = setlist_sections(items)
        self.assertEqual(out["main"], ["A", {"medley": ["M1", "M2"]}, "B"])
        self.assertEqual(out["encore"], ["E1"])
        self.assertEqual(out["wencore"], ["W1"])

    def test_medleys_in_different_sections_do_not_merge(self):
        items = [self.item("main", 1, 1, "A"), self.item("encore", 1, 1, "B")]
        out = setlist_sections(items)
        self.assertEqual(out["main"], [{"medley": ["A"]}])
        self.assertEqual(out["encore"], [{"medley": ["B"]}])
