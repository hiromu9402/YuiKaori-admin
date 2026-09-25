"""整合性チェックが、壊したデータを1つずつ検出できること。"""
import datetime

from catalog import models as m
from catalog.validate import validate

from .helpers import LegacyDataTestCase


class ValidateTests(LegacyDataTestCase):
    def assert_error(self, text):
        errors, _ = validate()
        self.assertTrue(any(text in e for e in errors), errors)

    def assert_warning(self, text):
        _, warnings = validate()
        self.assertTrue(any(text in w for w in warnings), warnings)

    def test_current_data_has_no_errors(self):
        errors, warnings = validate()
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def new_live(self, live_id="2026010101", date=datetime.date(2026, 1, 1), with_artist=True):
        live = m.Live.objects.create(id=live_id, title="テスト公演", date=date)
        if with_artist:
            m.LiveArtist.objects.create(live=live, artist=m.Artist.objects.get(name="小倉唯"))
        return live

    def test_id_date_mismatch(self):
        live = self.new_live(date=datetime.date(2026, 1, 2))
        m.SetlistItem.objects.create(live=live, pos=1, song=m.Song.objects.first())
        self.assert_error("公演IDの日付部分と開催日が違います")

    def test_bad_id_format(self):
        live = self.new_live(live_id="2026-01-01")
        m.SetlistItem.objects.create(live=live, pos=1, song=m.Song.objects.first())
        self.assert_error("公演IDの形式が正しくありません")

    def test_empty_setlist(self):
        self.new_live()
        self.assert_error("本編のセットリストが空です")

    def test_no_artist(self):
        live = self.new_live(with_artist=False)
        m.SetlistItem.objects.create(live=live, pos=1, song=m.Song.objects.first())
        self.assert_error("出演アーティストが設定されていません")

    def test_position_gap(self):
        live = self.new_live()
        m.SetlistItem.objects.create(live=live, pos=1, song=m.Song.objects.first())
        m.SetlistItem.objects.create(live=live, pos=3, song=m.Song.objects.last())
        self.assert_error("曲順が 1 から連続していません")

    def test_medley_numbering(self):
        live = self.new_live()
        m.SetlistItem.objects.create(live=live, pos=1, sub_pos=1, song=m.Song.objects.first())
        m.SetlistItem.objects.create(live=live, pos=1, sub_pos=3, song=m.Song.objects.last())
        self.assert_error("メドレー内の順番が正しくありません")

    def test_catalog_song_without_artist(self):
        m.Song.objects.create(title="アーティストなしの曲", in_catalog=True)
        self.assert_error("アーティストが設定されていません")

    def test_alias_conflicts_with_title(self):
        m.SongAlias.objects.create(alias="Raise", song=m.Song.objects.get(title="Raise"))
        self.assertEqual(validate()[0], [])  # 同じ曲を指すなら問題ない
        m.SongAlias.objects.filter(alias="Raise").update(song=m.Song.objects.get(title="Honey♥Come!!"))
        self.assert_error("別の曲の正式な曲名と同じです")

    def test_unreferenced_live_warning(self):
        live = self.new_live()
        m.SetlistItem.objects.create(live=live, pos=1, song=m.Song.objects.first())
        self.assertEqual(validate()[0], [])
        self.assert_warning("どのイベントからも参照されていない公演です")

    def test_variant_title_warning(self):
        m.Song.objects.create(title="Honey♡Come!!", in_catalog=False)
        self.assert_warning("表記ゆれの可能性がある曲名があります")

    def test_event_date_mismatch_warning(self):
        live = m.Live.objects.get(id="2025112401")
        m.Event.objects.create(date=datetime.date(2025, 11, 25), title="日付違い", live=live)
        self.assert_warning("イベントの日付と公演の開催日が違います")
