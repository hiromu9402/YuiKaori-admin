"""管理画面から使う処理（セットリストの保存、公演からのイベント作成、公開ファイルの書き出し）。"""
import subprocess
from collections import defaultdict

from django.conf import settings
from django.db import transaction

from . import models as m
from .exporter import write_all
from .normalize import clean, match_key, resolve
from .ordering import next_sort, place_by_date_desc
from .validate import validate


class SongIndex:
    """曲名から曲を引くための索引（正式な曲名・別表記・表記ゆれのキー）。"""

    def __init__(self):
        songs = list(m.Song.objects.all())
        self.by_title = {s.title: s for s in songs}
        self.aliases = {a.alias: a.song for a in m.SongAlias.objects.select_related("song")}
        self.by_key = defaultdict(list)
        for s in songs:
            self.by_key[match_key(s.title)].append(s)
        for alias, s in self.aliases.items():
            if s not in self.by_key[match_key(alias)]:
                self.by_key[match_key(alias)].append(s)

    def resolve(self, title):
        return resolve(title, self.by_title, self.aliases, self.by_key)


def unknown_titles(entries, index=None):
    """解決できない曲名と、その候補の曲: {曲名: [候補, ...]}（入力順）"""
    index = index or SongIndex()
    unknown = {}
    for e in entries:
        for t in e.titles:
            song, candidates = index.resolve(t)
            if song is None and t not in unknown:
                unknown[t] = candidates
    return unknown


@transaction.atomic
def register_titles(decisions):
    """未知の曲名の扱いを登録する。decisions: {曲名: ("alias", 曲) or ("new", None)}"""
    for title, (kind, song) in decisions.items():
        if kind == "alias":
            m.SongAlias.objects.create(alias=clean(title), song=song)
        elif kind == "new":
            m.Song.objects.create(title=clean(title), in_catalog=False, sort=next_sort(m.Song))
        else:
            raise ValueError(kind)


@transaction.atomic
def save_setlist(live, entries):
    """公演のセットリストを entries で置き換える。すべての曲名が解決できることが前提。"""
    index = SongIndex()
    items = []
    for e in entries:
        for k, t in enumerate(e.titles, start=1):
            song, _ = index.resolve(t)
            if song is None:
                raise ValueError(f"曲名を解決できません: {t}")
            items.append(m.SetlistItem(live=live, section=e.section, pos=e.pos, sub_pos=k if e.medley else 0, song=song))
    live.setlist_items.all().delete()
    m.SetlistItem.objects.bulk_create(items)
    return len(items)


@transaction.atomic
def create_event_for_live(live):
    """公演の日付・タイトル・会場・出演者を引き継いでイベントを作る。"""
    event = m.Event.objects.create(date=live.date, title=live.title, venue=live.venue, live=live, class1="ライブ")
    m.EventArtist.objects.bulk_create(
        m.EventArtist(event=event, artist=la.artist, ord=la.ord) for la in live.liveartist_set.all())
    place_by_date_desc(event)
    return event


def suggest_live_id(date):
    """開催日から、まだ使われていない公演ID（日付8桁＋連番2桁）を作る。"""
    prefix = date.strftime("%Y%m%d")
    used = set(m.Live.objects.filter(id__startswith=prefix).values_list("id", flat=True))
    for n in range(1, 100):
        candidate = f"{prefix}{n:02d}"
        if candidate not in used:
            return candidate
    raise ValueError(f"{date} の公演IDの連番が足りません")


def export_site():
    """整合性をチェックし、エラーがなければ公開用 JSON を書き出す。

    戻り値: {"errors", "warnings", "changed"（書き出したファイル）, "diffstat"（git diff --stat）}
    """
    errors, warnings = validate()
    result = {"errors": errors, "warnings": warnings, "changed": [], "diffstat": ""}
    if errors:
        return result
    result["changed"] = write_all(settings.SITE_DIR)
    result["diffstat"] = git_diffstat()
    return result


def git_diffstat():
    try:
        proc = subprocess.run(["git", "-C", str(settings.SITE_DIR), "diff", "--stat", "--", "*.json"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""
