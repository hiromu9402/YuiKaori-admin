"""取り込み→書き出しの統合テスト。"""
import datetime
import tempfile
from pathlib import Path

from catalog import models as m
from catalog.exporter import build_all, dumps, write_all

from .helpers import LegacyDataTestCase, load_legacy, normalize_legacy_event, normalize_legacy_live


class RoundTripTests(LegacyDataTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.exported = build_all()

    def test_import_warnings(self):
        # 旧版の my_c.html にある存在しない公演ID（本当は 2023080601）だけが警告になる
        self.assertEqual(len(self.import_warnings), 1, self.import_warnings)
        self.assertIn("2020120501", self.import_warnings[0])

    def test_counts(self):
        self.assertEqual(m.Song.objects.filter(in_catalog=True).count(), 187)
        self.assertEqual(m.CD.objects.count(), 73)
        self.assertEqual(m.Live.objects.count(), 190)
        self.assertEqual(m.Event.objects.count(), 1885)
        medleys = m.SetlistItem.objects.filter(sub_pos=1)
        self.assertEqual(medleys.filter(section=m.SetlistItem.MAIN).count(), 29)
        self.assertEqual(medleys.filter(section=m.SetlistItem.ENCORE).count(), 10)

    def test_songs_match(self):
        self.assertEqual(self.exported["song.json"], load_legacy("song.json"))

    def test_cds_match(self):
        self.assertEqual(self.exported["CD.json"], load_legacy("CD.json"))

    def test_setlists_match(self):
        self.assertEqual(self.exported["setlist.json"], [normalize_legacy_live(x) for x in load_legacy("setlist.json")])

    def test_events_match(self):
        self.assertEqual(self.exported["event.json"], [normalize_legacy_event(x) for x in load_legacy("event.json")])

    def test_key_order_is_kept(self):
        for name in ("song.json", "CD.json", "setlist.json", "event.json"):
            for new, old in zip(self.exported[name], load_legacy(name)):
                self.assertEqual([k for k in new], [k for k in old if k in new], name)

    def test_tour_options_match_legacy_html(self):
        from catalog.importer import parse_legacy_tour_html
        from .helpers import LEGACY_DIR
        legacy = parse_legacy_tour_html((LEGACY_DIR / "tour.html").read_text(encoding="utf-8"))
        exported = [(g["group"], t) for g in self.exported["tours.json"] for t in g["tours"]]
        self.assertEqual(exported, legacy)

    def test_checklist_matches_legacy_html(self):
        from catalog.importer import LEGACY_CHECKLIST_PAGES, parse_legacy_checklist_html
        from .helpers import LEGACY_DIR
        for page, artist in LEGACY_CHECKLIST_PAGES.items():
            legacy = parse_legacy_checklist_html((LEGACY_DIR / page).read_text(encoding="utf-8"))
            legacy = [(h, [(i, lab) for i, lab in es if i != "2020120501"]) for h, es in legacy]
            exported = [(g["heading"], [(e["id"], e["label"]) for e in g["lives"]])
                        for g in self.exported["checklist.json"][artist]]
            self.assertEqual(exported, legacy, page)

    def test_reimport_from_exported_files(self):
        """書き出した JSON（tours.json / checklist.json を含む）から作り直しても、同じ内容になること。"""
        from catalog.importer import import_site
        with tempfile.TemporaryDirectory() as tmp:
            write_all(tmp, self.exported)
            self.assertEqual(import_site(tmp), [])
            self.assertEqual(build_all(), self.exported)


class WriteTests(LegacyDataTestCase):
    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(len(write_all(tmp)), 6)
            before = {p.name: p.read_bytes() for p in Path(tmp).iterdir()}
            self.assertEqual(write_all(tmp), [])
            self.assertEqual({p.name: p.read_bytes() for p in Path(tmp).iterdir()}, before)

    def test_adding_a_live_changes_only_related_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_all(tmp)
            tour = m.Tour.objects.get(title="小倉唯 LIVE TOUR 2025「Love♡Ratory」")
            live = m.Live.objects.create(id="2026010101", title="テスト公演", tour=tour,
                                         date=datetime.date(2026, 1, 1), venue="テスト会場", sort=-1000)
            m.LiveArtist.objects.create(live=live, artist=m.Artist.objects.get(name="小倉唯"))
            m.SetlistItem.objects.create(live=live, pos=1, song=m.Song.objects.get(title="Raise"))
            event = m.Event.objects.create(date=live.date, title="テスト公演", live=live, sort=-1000)
            m.EventArtist.objects.create(event=event, artist=m.Artist.objects.get(name="小倉唯"))
            self.assertEqual(sorted(write_all(tmp)), ["event.json", "setlist.json"])
            setlist = build_all()["setlist.json"][0]
            self.assertEqual(setlist["id"], "2026010101")
            self.assertEqual(setlist["date"], "2026年1月1日")
            self.assertEqual(setlist["setlist"], ["Raise"])
            self.assertNotIn("encore", setlist)

    def test_output_format(self):
        text = dumps([{"title": "Raise"}])
        self.assertEqual(text, '[\n    {\n        "title": "Raise"\n    }\n]\n')
