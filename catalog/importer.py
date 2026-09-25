"""公開用の JSON（と、旧版の手書き HTML）から DB を作る。

最初の移行と、書き出した JSON から DB を作り直すときに使う。
- tours.json / checklist.json があればそれを読み、なければ旧版の tour.html / my*.html を解析する
- 既存のデータはすべて消してから取り込む（呼び出し側で確認すること）
"""
import datetime
import html
import json
import re
from pathlib import Path

from django.db import transaction

from . import models as m
from .normalize import clean

SORT_STEP = 1000
# 旧版のページとアーティストの対応、公開ページで使う CSS クラス
LEGACY_CHECKLIST_PAGES = {"my.html": "小倉唯", "my_c.html": "石原夏織", "my_f.html": "ゆいかおり"}
ARTIST_CLASSES = {"小倉唯": "artist1", "石原夏織": "artist2", "ゆいかおり": "artist3"}
ARTIST_ORDER = ["小倉唯", "石原夏織", "ゆいかおり", "StylipS", "RO-KYU-BU!"]


def as_list(value):
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def join_multi(value):
    return m.MULTI_SEP.join(clean(v) for v in as_list(value))


def parse_ja_date(s):
    y, mo, d = map(int, re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s).groups())
    return datetime.date(y, mo, d)


def parse_legacy_tour_html(text):
    """tour.html の <select id="tourSelect"> から ([(グループ名, ツアー名), ...], 初期選択のツアー名) を取り出す。"""
    sel = text[text.index('<select id="tourSelect"'):]
    sel = sel[:sel.index("</select>")]
    out, group, default = [], None, None
    for g in re.finditer(r'<optgroup label="([^"]*)"|<option value="([^"]+)"([^>]*)>', sel):
        if g.group(1) is not None:
            group = html.unescape(g.group(1))
        else:
            out.append((group, clean(html.unescape(g.group(2)))))
            if re.search(r"\bselected\b", g.group(3)):
                default = out[-1][1]
    return out, default


def parse_legacy_checklist_html(text):
    """my*.html から [(見出し, [(公演ID, 表示名), ...]), ...] を取り出す。"""
    body = text[text.index("<body"):]
    groups = []
    for g in re.finditer(r'<h3>(.*?)</h3>|<input type="checkbox" id="(\d+)" class="checkbox">([^<\n]*)', body):
        if g.group(1) is not None:
            groups.append((clean(html.unescape(re.sub(r"<[^>]+>", "", g.group(1)))), []))
        else:
            groups[-1][1].append((g.group(2), clean(html.unescape(g.group(3)))))
    return groups


def load_json(site_dir, name):
    return json.loads((Path(site_dir) / name).read_text(encoding="utf-8"))


@transaction.atomic
def import_site(site_dir):
    """site_dir の公開ファイルから DB を作り直す。警告メッセージのリストを返す。"""
    site_dir = Path(site_dir)
    warnings = []
    songs_json = load_json(site_dir, "song.json")
    cds_json = load_json(site_dir, "CD.json")
    lives_json = load_json(site_dir, "setlist.json")
    events_json = load_json(site_dir, "event.json")

    for model in (m.ChecklistEntry, m.ChecklistGroup, m.EventArtist, m.Event, m.SetlistItem, m.LiveArtist,
                  m.Live, m.Tour, m.SongAlias, m.SongCD, m.Song, m.CD, m.Artist):
        model.objects.all().delete()

    # アーティスト：決まった順番のあと、データに出てくる順
    names = list(ARTIST_ORDER)
    for n in ([x["artist"] for x in songs_json + cds_json]
              + [a for x in lives_json for a in as_list(x.get("artist"))]
              + [a for x in events_json for a in as_list(x["Artist"])]):
        if n and n not in names:
            names.append(n)
    artists = {n: m.Artist.objects.create(name=n, css_class=ARTIST_CLASSES.get(n, ""), sort=i * SORT_STEP)
               for i, n in enumerate(names)}

    cds = {}
    for i, x in enumerate(cds_json):
        cds[x["CDtitle"]] = m.CD.objects.create(
            title=clean(x["CDtitle"]), type=x["type"], artist=artists[x["artist"]],
            release_date=parse_ja_date(x["date"]), sort=i * SORT_STEP)

    songs = {}
    for i, x in enumerate(songs_json):
        song = m.Song.objects.create(
            title=clean(x["title"]), artist=artists[x["artist"]], in_catalog=True,
            lyrics=join_multi(x["lyrics"]), music=join_multi(x["music"]), arranger=join_multi(x["arranger"]),
            length=x["length"], utanet=x["utanet"], mv=x["MVlink"], dance=x["Dancelink"], video=x["videolink"],
            other=x["otherlink"], call=x["call"], info=x["info"], sort=i * SORT_STEP)
        songs[song.title] = song
        m.SongCD.objects.bulk_create(m.SongCD(song=song, cd=cds[t], ord=j) for j, t in enumerate(as_list(x["CDtitle"])))
    next_song_sort = len(songs_json) * SORT_STEP

    def song_for(title):
        nonlocal next_song_sort
        title = clean(title)
        if title not in songs:
            # セットリストにしか出てこない曲（カバーなど）
            songs[title] = m.Song.objects.create(title=title, in_catalog=False, sort=next_song_sort)
            next_song_sort += SORT_STEP
        return songs[title]

    tours = {}

    def tour_for(title):
        title = clean(title)
        if not title:
            return None
        if title not in tours:
            tours[title] = m.Tour.objects.create(title=title)
        return tours[title]

    lives = {}
    sections = [("setlist", m.SetlistItem.MAIN), ("encore", m.SetlistItem.ENCORE), ("Wencore", m.SetlistItem.WENCORE)]
    for i, x in enumerate(lives_json):
        if x["id"] in lives:
            warnings.append(f"公演IDが重複しているので2件目以降を取り込みませんでした: {x['id']} {x['LIVEtitle']}")
            continue
        live = m.Live.objects.create(id=x["id"], title=clean(x["LIVEtitle"]), tour=tour_for(x["tourtitle"]),
                                     date=parse_ja_date(x["date"]), venue=x["venue"], sort=i * SORT_STEP)
        lives[live.id] = live
        m.LiveArtist.objects.bulk_create(
            m.LiveArtist(live=live, artist=artists[a], ord=j) for j, a in enumerate(as_list(x.get("artist"))))
        items = []
        for key, section in sections:
            for pos, entry in enumerate(as_list(x.get(key)), start=1):
                if isinstance(entry, dict):
                    items += [m.SetlistItem(live=live, section=section, pos=pos, sub_pos=k, song=song_for(t))
                              for k, t in enumerate(entry["medley"], start=1)]
                else:
                    items.append(m.SetlistItem(live=live, section=section, pos=pos, song=song_for(entry)))
        m.SetlistItem.objects.bulk_create(items)

    for i, x in enumerate(events_json):
        live = None
        if x["id"]:
            live = lives.get(x["id"])
            if live is None:
                warnings.append(f"イベントの公演IDに対応する公演がありません: {x['id']} {x['title']}")
        event = m.Event.objects.create(
            date=datetime.date(int(x["Year"]), int(x["Month"]), int(x["Day"])), start_time=x["Start Time"],
            class1=x["class1"], class2=x["class2"], class3=x["class3"], title=x["title"], title2=x["title2"],
            prefecture=x["prefecture"], venue=x["Venue"], sponsor=x["sponsor"], info=x["info"], live=live,
            sort=i * SORT_STEP)
        m.EventArtist.objects.bulk_create(
            m.EventArtist(event=event, artist=artists[a], ord=j) for j, a in enumerate(as_list(x["Artist"])))

    # ツアー比較ページの選択肢
    if (site_dir / "tours.json").exists():
        tours_json = load_json(site_dir, "tours.json")
        compare = [(g["group"], t) for g in tours_json["groups"] for t in g["tours"]]
        default = tours_json.get("default")
    else:
        compare, default = parse_legacy_tour_html((site_dir / "tour.html").read_text(encoding="utf-8"))
    for i, (group, title) in enumerate(compare):
        tour = tours.get(title)
        if tour is None:
            warnings.append(f"比較ページの選択肢に対応するツアーがありません: {title}")
            continue
        tour.compare_artist = artists[group]
        tour.compare_sort = i * SORT_STEP
        tour.compare_default = title == default
        tour.save()

    # 未回収楽曲チェック
    if (site_dir / "checklist.json").exists():
        pages = [(name, [(g["heading"], [(e["id"], e["label"]) for e in g["lives"]]) for g in groups])
                 for name, groups in load_json(site_dir, "checklist.json").items()]
    else:
        pages = [(artist, parse_legacy_checklist_html((site_dir / page).read_text(encoding="utf-8")))
                 for page, artist in LEGACY_CHECKLIST_PAGES.items()]
    for artist, groups in pages:
        for gi, (heading, entries) in enumerate(groups):
            group = m.ChecklistGroup.objects.create(artist=artists[artist], heading=heading, sort=gi * SORT_STEP)
            for ei, (live_id, label) in enumerate(entries):
                if live_id not in lives:
                    warnings.append(f"未回収チェック（{artist}）の公演IDに対応する公演がありません: {live_id} {label}")
                    continue
                m.ChecklistEntry.objects.create(group=group, live=lives[live_id], label=label, sort=ei * SORT_STEP)
    return warnings
