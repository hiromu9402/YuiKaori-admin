"""データの整合性チェック。書き出しの前に必ず実行する。

ID の重複や存在しない参照は DB の制約で防がれるので、ここでは制約で表せないものを調べる。
戻り値は (エラーのリスト, 警告のリスト)。エラーが1件でもあれば書き出さない。
"""
from collections import defaultdict

from . import models as m
from .normalize import match_key


def validate():
    errors, warnings = [], []

    for live in m.Live.objects.prefetch_related("setlist_items", "liveartist_set", "events"):
        if not m.live_id_validator.regex.match(live.id):
            errors.append(f"公演IDの形式が正しくありません: {live.id}")
        elif live.id[:8] != live.date.strftime("%Y%m%d"):
            errors.append(f"公演IDの日付部分と開催日が違います: {live.id}（開催日 {live.date}）")
        items = list(live.setlist_items.all())
        if not any(i.section == m.SetlistItem.MAIN for i in items):
            errors.append(f"本編のセットリストが空です: {live}")
        if not live.liveartist_set.all():
            errors.append(f"出演アーティストが設定されていません: {live}")
        errors += [f"{live}: {msg}" for msg in check_positions(items)]
        if not live.events.all():
            warnings.append(f"どのイベントからも参照されていない公演です: {live}")

    for song in m.Song.objects.filter(in_catalog=True, artist__isnull=True):
        errors.append(f"楽曲一覧に載せる曲にアーティストが設定されていません: {song}")

    titles = {s.title: s for s in m.Song.objects.all()}
    for alias in m.SongAlias.objects.select_related("song"):
        other = titles.get(alias.alias)
        if other is not None and other != alias.song:
            errors.append(f"別表記「{alias.alias}」が別の曲の正式な曲名と同じです（{alias.song} と {other}）")

    for e in m.Event.objects.select_related("live").filter(live__isnull=False):
        if e.live.date != e.date:
            warnings.append(f"イベントの日付と公演の開催日が違います: {e}（公演 {e.live}）")

    by_key = defaultdict(list)
    for s in titles.values():
        by_key[match_key(s.title)].append(s)
    for key, songs in by_key.items():
        if len(songs) > 1:
            names = "、".join(sorted(s.title for s in songs))
            warnings.append(f"表記ゆれの可能性がある曲名があります: {names}（同じ曲なら別表記として統合してください）")
    return errors, warnings


def check_positions(items):
    """区分ごとに曲順が 1 から連続しているか、メドレーの番号が正しいかを調べる。"""
    msgs = []
    by_section = defaultdict(lambda: defaultdict(list))
    for it in items:
        by_section[it.section][it.pos].append(it.sub_pos)
    labels = dict(m.SetlistItem.SECTIONS)
    for section, positions in by_section.items():
        if sorted(positions) != list(range(1, len(positions) + 1)):
            msgs.append(f"{labels[section]}の曲順が 1 から連続していません: {sorted(positions)}")
        for pos, subs in positions.items():
            subs = sorted(subs)
            if subs != [0] and subs != list(range(1, len(subs) + 1)):
                msgs.append(f"{labels[section]} {pos}曲目のメドレー内の順番が正しくありません: {subs}")
    return msgs
