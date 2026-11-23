import csv
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Live

HELP_FORMAT = """CSV の列（1行目は見出し）:
  live_id  公演ID（必須）
  status   照合の状態（必須）。ok / fixed / partial / doubt / notfound か、表示名（一致・修正済み など）
  date     照合日（YYYY-MM-DD）。空なら今日
  source   出典（URL や資料名）。複数は「 | 」で区切ると、1行に1つずつ入る。空なら今の値のまま
  note     メモ。空なら今の値のまま
"""


def parse_status(value):
    value = value.strip()
    for code, label in Live.VERIFY_CHOICES:
        if value in (code, label) and code:
            return code
    raise ValueError(f"照合の状態が分かりません: {value!r}")


class Command(BaseCommand):
    help = "公演の照合の記録（状態・照合日・出典・メモ）を CSV からまとめて書き込む。--apply を付けないと、差分を表示するだけ"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", help="CSV ファイル（UTF-8）\n" + HELP_FORMAT)
        parser.add_argument("--apply", action="store_true", help="実際に書き込む（付けないときは差分の表示だけ）")

    def handle(self, csv_file, apply, **options):
        with open(csv_file, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        missing = {"live_id", "status"} - set(rows[0].keys() if rows else [])
        if missing:
            raise CommandError(f"CSV に必要な列がありません: {', '.join(sorted(missing))}\n{HELP_FORMAT}")

        # すべての行を先に確かめ、1行でも誤りがあれば何も書き込まない
        errors, plans = [], []
        for n, row in enumerate(rows, start=2):
            try:
                live = Live.objects.get(pk=(row.get("live_id") or "").strip())
            except Live.DoesNotExist:
                errors.append(f"{n} 行目: 公演が見つかりません: {row.get('live_id')!r}")
                continue
            try:
                new = {
                    "verify_status": parse_status(row.get("status") or ""),
                    "verify_date": date.fromisoformat(row["date"].strip()) if (row.get("date") or "").strip() else date.today(),
                }
            except ValueError as e:
                errors.append(f"{n} 行目: {e}")
                continue
            if (row.get("source") or "").strip():
                new["verify_source"] = "\n".join(s.strip() for s in row["source"].split("|") if s.strip())
            if (row.get("note") or "").strip():
                new["verify_note"] = row["note"].strip()
            diff = {k: (getattr(live, k), v) for k, v in new.items() if getattr(live, k) != v}
            plans.append((live, diff))
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(e))
            raise CommandError(f"誤りが {len(errors)} 件あるので、何も書き込みませんでした")

        labels = dict(Live.VERIFY_CHOICES)
        show = lambda k, v: labels.get(v, v) if k == "verify_status" else v  # noqa: E731
        for live, diff in plans:
            if not diff:
                self.stdout.write(f"{live.pk} {live.title}: 変更なし")
                continue
            self.stdout.write(f"{live.pk} {live.title}:")
            for k, (old, new) in diff.items():
                self.stdout.write(f"  {Live._meta.get_field(k).verbose_name}: {show(k, old)!r} → {show(k, new)!r}")
        count = sum(1 for _, d in plans if d)
        if not apply:
            self.stdout.write(self.style.WARNING(f"{count} 件の公演が変わります。書き込むときは --apply を付けて実行してください"))
            return
        with transaction.atomic():
            for live, diff in plans:
                if diff:
                    for k, (_, new) in diff.items():
                        setattr(live, k, new)
                    live.save(update_fields=list(diff))
        self.stdout.write(self.style.SUCCESS(f"{count} 件の公演の照合の記録を書き込みました"))
