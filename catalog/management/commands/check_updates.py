import os
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog import updates


class Command(BaseCommand):
    help = ("データ更新の候補（外部のイベント一覧にあって DB にないイベント、セットリストがない過去のライブ、"
            "これから 1 か月のライブ）を集めて、管理画面のトップに出す。--notify で LINE にも知らせる")

    def add_arguments(self, parser):
        parser.add_argument("--notify", action="store_true",
                            help="LINE に知らせる（YUIKAORI_LINE_NOTIFY のコマンド。既定は ~/.local/bin/line-notify）")
        parser.add_argument("--dry-run", action="store_true", help="結果を表示するだけで、保存も通知もしない")

    def handle(self, notify, dry_run, **options):
        report = updates.build_report()
        for e in report["new_events"]:
            self.stdout.write(f"新しいイベント: {e['date']} {e['title']}（{e['venue']}） {e['url']}")
        for e in report["missing_setlists"]:
            self.stdout.write(f"セットリストなし: {e['date']} {e['title']}")
        for e in report["upcoming"]:
            self.stdout.write(f"これから: {e['date']} {e['title']}")
        if not report["source_enabled"]:
            self.stdout.write(f"外部のイベント一覧の設定（{updates.sources_path()}）がないので、読んでいません")
        for msg in report["errors"]:
            self.stdout.write(self.style.WARNING(msg))
        text = updates.summary(report, os.environ.get("YUIKAORI_ADMIN_URL", ""))
        self.stdout.write(text)
        if dry_run:
            return
        updates.save_report(report)
        if notify:
            command = os.environ.get("YUIKAORI_LINE_NOTIFY") or str(Path.home() / ".local/bin/line-notify")
            proc = subprocess.run([command, text], capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                raise CommandError(f"LINE に送れませんでした: {(proc.stderr or proc.stdout).strip()[:300]}")
            self.stdout.write(self.style.SUCCESS("LINE に知らせました"))
