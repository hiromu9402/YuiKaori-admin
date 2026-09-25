"""セットリストのテキスト形式（管理画面の一括入力）。

    Love∞Vision
    [メドレー] LOVE涙色 / ラムのラブソング / Baby, Baby, Baby♡
    == アンコール
    winter tale
    == Wアンコール
    治癒治癒ちゅっ♡

- 1行に1曲。空行は無視する
- 「[メドレー]」で始まる行は、「 / 」（前後に空白のあるスラッシュ）で区切った曲をメドレーとして扱う
- 「== 本編」「== アンコール」「== Wアンコール」で区分を切り替える（最初は本編）
"""
from dataclasses import dataclass, field

from . import models as m
from .normalize import clean

MEDLEY_PREFIX = "[メドレー]"
MEDLEY_SEP = " / "
SECTION_HEADERS = {
    "本編": m.SetlistItem.MAIN,
    "アンコール": m.SetlistItem.ENCORE,
    "Wアンコール": m.SetlistItem.WENCORE,
}
SECTION_LABELS = {v: k for k, v in SECTION_HEADERS.items()}


class SetlistSyntaxError(ValueError):
    pass


@dataclass
class Entry:
    section: str
    pos: int
    titles: list = field(default_factory=list)
    medley: bool = False


def parse(text):
    """テキストを Entry のリストにする。書き方が間違っていれば SetlistSyntaxError。"""
    entries, section, pos = [], m.SetlistItem.MAIN, {}
    seen_sections = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = clean(raw)
        if not line:
            continue
        if line.startswith("=="):
            name = clean(line[2:])
            if name not in SECTION_HEADERS:
                raise SetlistSyntaxError(
                    f"{lineno}行目: 区分「{name}」はわかりません（本編・アンコール・Wアンコール のどれかを書いてください）")
            section = SECTION_HEADERS[name]
            if section in seen_sections:
                raise SetlistSyntaxError(f"{lineno}行目: 区分「{name}」が2回出てきます")
            seen_sections.add(section)
            continue
        pos[section] = pos.get(section, 0) + 1
        if line.startswith(MEDLEY_PREFIX):
            titles = _split_medley(line[len(MEDLEY_PREFIX):])
            if not titles:
                raise SetlistSyntaxError(f"{lineno}行目: メドレーの曲がありません")
            entries.append(Entry(section, pos[section], titles, medley=True))
        else:
            entries.append(Entry(section, pos[section], [line]))
    if not any(e.section == m.SetlistItem.MAIN for e in entries):
        raise SetlistSyntaxError("本編の曲がありません")
    return entries


def _split_medley(text):
    # 曲名に含まれる「//」（Empty//Princess. など）で切らないよう、前後に空白のある「 / 」だけで区切る
    return [clean(t) for t in f" {clean(text)} ".split(MEDLEY_SEP) if clean(t)]


def to_text(live):
    """公演の今のセットリストをテキスト形式にする（一括入力の初期値）。"""
    lines, current = [], m.SetlistItem.MAIN
    items = sorted(live.setlist_items.select_related("song"),
                   key=lambda i: ([s for s, _ in m.SetlistItem.SECTIONS].index(i.section), i.pos, i.sub_pos))
    groups = []
    for it in items:
        if groups and groups[-1][0] == (it.section, it.pos):
            groups[-1][1].append(it)
        else:
            groups.append(((it.section, it.pos), [it]))
    for (section, _), its in groups:
        if section != current:
            lines.append(f"== {SECTION_LABELS[section]}")
            current = section
        if its[0].sub_pos:
            lines.append(f"{MEDLEY_PREFIX} " + MEDLEY_SEP.join(i.song.title for i in its))
        else:
            lines.append(its[0].song.title)
    return "\n".join(lines)
