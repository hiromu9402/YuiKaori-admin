"""公開中の JSON（公開サイトのリポジトリ）と、DB から作った JSON の違いをまとめる。

export_json --check と、管理画面（トップ・書き出し・プレビュー）で使う。
"""
import json
from pathlib import Path

from .exporter import build_all, dumps

# どの項目が増えた・減った・変わったかを示すときの見出し
LABELS = {
    "song.json": lambda x: x.get("title"),
    "CD.json": lambda x: x.get("CDtitle"),
    "setlist.json": lambda x: f"{x.get('id')} {x.get('LIVEtitle')}",
    "event.json": lambda x: f"{x.get('Year')}/{x.get('Month')}/{x.get('Day')} {x.get('title')}",
}
# 同じものかどうかを決める項目（変わった、として数えるため）。ないものは中身全体で比べる
KEYS = {"song.json": "title", "CD.json": "CDtitle", "setlist.json": "id"}


def describe(name, old, new, limit=10):
    """old から new への変化を、人が読める行のリストにする。"""
    if not isinstance(old, list) or not isinstance(new, list) or name not in LABELS:
        return ["中身が変わる"]
    label = LABELS[name]
    key = KEYS.get(name)
    if key:
        old_by = {x.get(key): x for x in old}
        new_by = {x.get(key): x for x in new}
        added = [new_by[k] for k in new_by if k not in old_by]
        removed = [old_by[k] for k in old_by if k not in new_by]
        changed = [new_by[k] for k in new_by if k in old_by and old_by[k] != new_by[k]]
    else:
        as_text = lambda xs: [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in xs]  # noqa: E731
        old_t, new_t = as_text(old), as_text(new)
        old_set, new_set = set(old_t), set(new_t)
        added = [x for x, t in zip(new, new_t) if t not in old_set]
        removed = [x for x, t in zip(old, old_t) if t not in new_set]
        changed = []
    lines = [f"{len(old)} 件 → {len(new)} 件（追加 {len(added)}・削除 {len(removed)}・変更 {len(changed)}）"]
    for mark, items in (("+", added), ("-", removed), ("~", changed)):
        lines += [f"  {mark} {label(x)}" for x in items[:limit]]
        if len(items) > limit:
            lines.append(f"  {mark} ほか {len(items) - limit} 件")
    return lines


def changes(site_dir, data=None):
    """[{"name": ファイル名, "lines": [説明の行]}] を返す。変わらないファイルは入れない。"""
    site_dir = Path(site_dir)
    data = build_all() if data is None else data
    result = []
    for name, value in data.items():
        path = site_dir / name
        old_text = path.read_text(encoding="utf-8") if path.exists() else None
        if old_text == dumps(value):
            continue
        lines = ["新しく作る"] if old_text is None else describe(name, json.loads(old_text), value)
        result.append({"name": name, "lines": lines})
    return result
