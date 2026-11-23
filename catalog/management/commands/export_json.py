import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.exporter import build_all, dumps, write_all
from catalog.validate import validate

# --check で、どの項目が増えた・減った・変わったかを示すときの見出し
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


class Command(BaseCommand):
    help = "整合性をチェックしてから、公開用の JSON を書き出す（--check で、書き出さずに変わる内容だけを表示する）"

    def add_arguments(self, parser):
        parser.add_argument("--site-dir", default=str(settings.SITE_DIR), help="書き出し先")
        parser.add_argument("--check", action="store_true", help="書き出さずに、今の公開ファイルから何が変わるかを表示する")

    def handle(self, site_dir, check, **options):
        errors, warnings = validate()
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"エラー: {e}"))
            raise CommandError(f"エラーが {len(errors)} 件あるので書き出しませんでした")
        if check:
            return self.show_changes(Path(site_dir), len(warnings))
        changed = write_all(site_dir)
        self.stdout.write(self.style.SUCCESS(
            f"{site_dir} に書き出しました。変更: {', '.join(changed) if changed else 'なし'}（警告 {len(warnings)} 件）"))

    def show_changes(self, site_dir, warnings):
        changed = []
        for name, value in build_all().items():
            path = site_dir / name
            old_text = path.read_text(encoding="utf-8") if path.exists() else None
            if old_text == dumps(value):
                continue
            changed.append(name)
            self.stdout.write(f"{name}:")
            lines = ["新しく作る"] if old_text is None else describe(name, json.loads(old_text), value)
            for line in lines:
                self.stdout.write(f"  {line}")
        summary = f"変わるファイル: {', '.join(changed) if changed else 'なし'}（警告 {warnings} 件。書き出してはいません）"
        self.stdout.write(self.style.SUCCESS(summary))
