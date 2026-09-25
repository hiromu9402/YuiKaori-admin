"""DB から公開用の JSON を作る。

キー名・日付の書式・並び順は旧版の JSON と同じにしている（公開ページの JavaScript がそのまま動くように）。
型だけは揃えていて、setlist / encore / Wencore は常に配列、encore と Wencore は空ならキーを出さない。
アーティスト・作詞などの複数になりうる欄は「1つなら文字列、複数なら配列」にする。
"""
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

from django.db.models import Prefetch

from . import models as m

EXPORT_FILES = ["song.json", "CD.json", "setlist.json", "event.json", "tours.json", "checklist.json"]


def one_or_many(values):
    values = list(values)
    if not values:
        return ""
    return values[0] if len(values) == 1 else values


def ja_date(d):
    return f"{d.year}年{d.month}月{d.day}日"


def export_songs():
    songs = (m.Song.objects.filter(in_catalog=True).select_related("artist")
             .prefetch_related(Prefetch("songcd_set", queryset=m.SongCD.objects.select_related("cd"))))
    return [{
        "title": s.title,
        "artist": s.artist.name if s.artist else "",
        "lyrics": one_or_many(m.split_multi(s.lyrics)),
        "music": one_or_many(m.split_multi(s.music)),
        "arranger": one_or_many(m.split_multi(s.arranger)),
        "length": s.length,
        "CDtitle": one_or_many(sc.cd.title for sc in s.songcd_set.all()),
        "utanet": s.utanet,
        "MVlink": s.mv,
        "Dancelink": s.dance,
        "videolink": s.video,
        "otherlink": s.other,
        "call": s.call,
        "info": s.info,
    } for s in songs]


def export_cds():
    return [{"CDtitle": c.title, "type": c.type, "artist": c.artist.name, "date": ja_date(c.release_date)}
            for c in m.CD.objects.select_related("artist")]


def setlist_sections(items):
    """SetlistItem のリストを {区分: [曲名 or {"medley": [...]}, ...]} にまとめる。"""
    out = defaultdict(list)
    medley_at = {}
    for it in sorted(items, key=lambda i: (i.pos, i.sub_pos)):
        if it.sub_pos == 0:
            out[it.section].append(it.song.title)
        else:
            key = (it.section, it.pos)
            if key not in medley_at:
                medley_at[key] = {"medley": []}
                out[it.section].append(medley_at[key])
            medley_at[key]["medley"].append(it.song.title)
    return out


def export_lives():
    lives = m.Live.objects.select_related("tour").prefetch_related(
        Prefetch("liveartist_set", queryset=m.LiveArtist.objects.select_related("artist")),
        Prefetch("setlist_items", queryset=m.SetlistItem.objects.select_related("song")))
    result = []
    for live in lives:
        row = {"LIVEtitle": live.title, "tourtitle": live.tour.title if live.tour else ""}
        artist = one_or_many(la.artist.name for la in live.liveartist_set.all())
        if artist:
            row["artist"] = artist
        row.update({"date": ja_date(live.date), "venue": live.venue, "id": live.id})
        sections = setlist_sections(live.setlist_items.all())
        row["setlist"] = sections[m.SetlistItem.MAIN]
        if sections[m.SetlistItem.ENCORE]:
            row["encore"] = sections[m.SetlistItem.ENCORE]
        if sections[m.SetlistItem.WENCORE]:
            row["Wencore"] = sections[m.SetlistItem.WENCORE]
        result.append(row)
    return result


def export_events():
    events = m.Event.objects.prefetch_related(
        Prefetch("eventartist_set", queryset=m.EventArtist.objects.select_related("artist")))
    return [{
        "Artist": one_or_many(ea.artist.name for ea in e.eventartist_set.all()),
        "Year": str(e.date.year),
        "Month": str(e.date.month),
        "Day": str(e.date.day),
        "Weekday": e.weekday,
        "Start Time": e.start_time,
        "class1": e.class1,
        "class2": e.class2,
        "class3": e.class3,
        "title": e.title,
        "title2": e.title2,
        "prefecture": e.prefecture,
        "Venue": e.venue,
        "sponsor": e.sponsor,
        "info": e.info,
        "id": e.live_id or "",
    } for e in events]


def export_tours():
    """tour.html の選択肢: {"groups": [{"group": アーティスト名, "tours": [ツアー名, ...]}, ...], "default": 初期選択}"""
    groups, default = {}, None
    for t in (m.Tour.objects.filter(compare_artist__isnull=False).select_related("compare_artist")
              .order_by("compare_artist__sort", "compare_sort", "title")):
        groups.setdefault(t.compare_artist.name, []).append(t.title)
        if t.compare_default and default is None:
            default = t.title
    return {"groups": [{"group": g, "tours": ts} for g, ts in groups.items()], "default": default}


def export_checklist():
    """my*.html の見出しと公演: {アーティスト名: [{"heading": 見出し, "lives": [{"id", "label"}]}, ...]}"""
    out = {}
    for g in m.ChecklistGroup.objects.select_related("artist").prefetch_related("entries"):
        out.setdefault(g.artist.name, []).append(
            {"heading": g.heading, "lives": [{"id": e.live_id, "label": e.label} for e in g.entries.all()]})
    return out


def build_all():
    """{ファイル名: データ} を返す。"""
    return {
        "song.json": export_songs(),
        "CD.json": export_cds(),
        "setlist.json": export_lives(),
        "event.json": export_events(),
        "tours.json": export_tours(),
        "checklist.json": export_checklist(),
    }


def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=4) + "\n"


def write_all(site_dir, data=None):
    """site_dir に JSON を書き出す。内容が変わったファイル名のリストを返す。

    途中で失敗しても公開ファイルが壊れないよう、一時ファイルに書いてから置き換える。
    """
    site_dir = Path(site_dir)
    data = build_all() if data is None else data
    changed = []
    for name, value in data.items():
        path = site_dir / name
        text = dumps(value)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        fd, tmp = tempfile.mkstemp(dir=site_dir, prefix=f".{name}.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        changed.append(name)
    return changed
