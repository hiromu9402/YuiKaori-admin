import datetime

from django.test import SimpleTestCase

from catalog import models as m
from catalog.ordering import place_by_date_desc
from catalog.services import suggest_live_id
from catalog.setlist_text import Entry, SetlistSyntaxError, parse, to_text

from .helpers import LegacyDataTestCase


class ParseTests(SimpleTestCase):
    def test_sections_and_medley(self):
        text = """
          Love∞Vision

        [メドレー] LOVE涙色 / ラムのラブソング / Baby, Baby, Baby♡
        花占いするの♡
        == アンコール
        winter tale
        == Wアンコール
        治癒治癒ちゅっ♡
        """
        self.assertEqual(parse(text), [
            Entry("main", 1, ["Love∞Vision"]),
            Entry("main", 2, ["LOVE涙色", "ラムのラブソング", "Baby, Baby, Baby♡"], medley=True),
            Entry("main", 3, ["花占いするの♡"]),
            Entry("encore", 1, ["winter tale"]),
            Entry("wencore", 1, ["治癒治癒ちゅっ♡"]),
        ])

    def test_double_slash_in_title_is_not_a_separator(self):
        entries = parse("[メドレー] Empty//Princess. / Raise")
        self.assertEqual(entries[0].titles, ["Empty//Princess.", "Raise"])

    def test_nfc(self):
        self.assertEqual(parse("半透明の世界で")[0].titles, ["半透明の世界で"])

    def test_errors(self):
        cases = {
            "== 本編2\nRaise": "区分「本編2」はわかりません",
            "Raise\n== アンコール\nA\n== アンコール\nB": "2回出てきます",
            "[メドレー]  ": "メドレーの曲がありません",
            "== アンコール\nRaise": "本編の曲がありません",
            "": "本編の曲がありません",
        }
        for text, message in cases.items():
            with self.subTest(text=text):
                with self.assertRaisesMessage(SetlistSyntaxError, message):
                    parse(text)


class TextRoundTripTests(LegacyDataTestCase):
    def test_every_live_round_trips(self):
        """すべての公演で、テキストにして読み直すと元のセットリストと同じになること。"""
        for live in m.Live.objects.prefetch_related("setlist_items__song"):
            items = sorted((i.section, i.pos, i.sub_pos, i.song.title) for i in live.setlist_items.all())
            parsed = sorted((e.section, e.pos, k if e.medley else 0, t)
                            for e in parse(to_text(live)) for k, t in enumerate(e.titles, start=1))
            self.assertEqual(parsed, items, live.id)


class SuggestIdAndOrderingTests(LegacyDataTestCase):
    def test_suggest_live_id(self):
        self.assertEqual(suggest_live_id(datetime.date(2030, 1, 1)), "2030010101")
        # 2025/11/24 には 01 と 02 がある
        self.assertEqual(suggest_live_id(datetime.date(2025, 11, 24)), "2025112403")

    def test_suggest_live_id_fills_gap(self):
        m.Live.objects.create(id="2030010102", title="x", date=datetime.date(2030, 1, 1))
        self.assertEqual(suggest_live_id(datetime.date(2030, 1, 1)), "2030010101")

    def ids_in_order(self):
        return list(m.Live.objects.order_by("sort").values_list("id", flat=True))

    def test_place_newest_first(self):
        live = m.Live.objects.create(id="2030010101", title="x", date=datetime.date(2030, 1, 1), sort=999999)
        place_by_date_desc(live)
        self.assertEqual(self.ids_in_order()[0], "2030010101")

    def test_place_in_middle_and_after_same_date(self):
        live = m.Live.objects.create(id="2025112403", title="x", date=datetime.date(2025, 11, 24))
        place_by_date_desc(live)
        ids = self.ids_in_order()
        # 同じ日付の既存の公演（01・02）の後ろで、それより古い公演の前
        self.assertLess(ids.index("2025112401"), ids.index("2025112403"))
        self.assertLess(ids.index("2025112402"), ids.index("2025112403"))
        self.assertLess(ids.index("2025112403"), ids.index("2025110201"))

    def test_place_oldest_last(self):
        live = m.Live.objects.create(id="2000010101", title="x", date=datetime.date(2000, 1, 1))
        place_by_date_desc(live)
        self.assertEqual(self.ids_in_order()[-1], "2000010101")

    def test_renumber_when_no_gap(self):
        # 日付が2日以上離れた隣り合う2件を探し、sort を詰めて間に入れる余地をなくす
        lives = list(m.Live.objects.order_by("sort"))
        newer, older = next((a, b) for a, b in zip(lives, lives[1:]) if (a.date - b.date).days >= 2)
        m.Live.objects.filter(pk=older.pk).update(sort=newer.sort + 1)
        date = older.date + datetime.timedelta(days=1)
        live = m.Live.objects.create(id=date.strftime("%Y%m%d") + "01", title="x", date=date)
        place_by_date_desc(live)
        ids = self.ids_in_order()
        self.assertEqual(ids.index(live.id), ids.index(newer.id) + 1)
        self.assertEqual(ids.index(older.id), ids.index(live.id) + 1)
        self.assertEqual(len(set(m.Live.objects.values_list("sort", flat=True))), m.Live.objects.count())
