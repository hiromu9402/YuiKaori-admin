import re
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "DB を保存先の backup/ に写す（サービスが動いている最中でも壊れない、SQLite の backup を使う）"

    def add_arguments(self, parser):
        parser.add_argument("--label", default="", help="ファイル名に付ける名前（英数字・-・_）。例: before-add-live")
        parser.add_argument("--dir", default=None, help="写す先のディレクトリ（既定は保存先の backup/）")

    def handle(self, label, dir, **options):
        if label and not re.fullmatch(r"[A-Za-z0-9_-]+", label):
            raise CommandError("--label に使えるのは英数字と - _ だけです")
        src = Path(settings.DATABASES["default"]["NAME"])
        if not src.exists():
            raise CommandError(f"DB がありません: {src}")
        out_dir = Path(dir) if dir else Path(settings.DATA_DIR) / "backup"
        out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        name = f"db-{datetime.now():%Y%m%d-%H%M%S}" + (f"-{label}" if label else "") + ".sqlite3"
        dest = out_dir / name
        if dest.exists():
            raise CommandError(f"同じ名前のファイルがあります: {dest}")
        # 読み取り専用で開き、書き込み中でも一貫した状態を写す
        with sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30) as a, sqlite3.connect(dest) as b:
            a.backup(b)
        dest.chmod(0o600)
        with sqlite3.connect(f"file:{dest}?mode=ro", uri=True) as c:
            check = c.execute("pragma integrity_check").fetchone()[0]
        if check != "ok":
            raise CommandError(f"写した DB の検査で問題が見つかりました（{check}）: {dest}")
        self.stdout.write(self.style.SUCCESS(f"{dest} に写しました（{dest.stat().st_size:,} バイト）"))
