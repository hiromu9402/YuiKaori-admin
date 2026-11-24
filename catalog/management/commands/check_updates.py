import os
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog import updates


class Command(BaseCommand):
    help = ("データ更新の候補（外部のイベント一覧にあって DB にないイベント、セットリストがない過去のライブ、"
            "これから 1 か月のライブ、新しい版が出たパッケージ）を集めて、管理画面のトップに出す。--notify で LINE にも知らせる。"
            "--notify-new なら、前回から新しい候補が増えたときだけ知らせる")

    def add_arguments(self, parser):
        parser.add_argument("--notify", action="store_true",
                            help="LINE に知らせる（YUIKAORI_LINE_NOTIFY のコマンド。既定は ~/.local/bin/line-notify）")
        parser.add_argument("--notify-new", action="store_true",
                            help="前回から新しい候補が増えたときだけ、増えた分を LINE に知らせる（毎週の cron 用）")
        parser.add_argument("--dry-run", action="store_true", help="結果を表示するだけで、保存も通知もしない")

    def handle(self, notify, notify_new, dry_run, **options):
        report = updates.build_report()
        new_count = updates.mark_new(report, updates.load_report())
        for e in report["new_events"]:
            self.stdout.write(f"新しいイベント: {e['date']} {e['title']}（{e['venue']}） {e['url']}")
        for e in report["missing_setlists"]:
            self.stdout.write(f"セットリストなし: {e['date']} {e['title']}")
        for e in report["upcoming"]:
            self.stdout.write(f"これから: {e['date']} {e['title']}")
        for p in report["outdated_packages"]:
            self.stdout.write(f"新しい版: {p['title']}（{p['date']} 公開） {p['url']}")
        if not report["source_enabled"]:
            self.stdout.write(f"外部のイベント一覧の設定（{updates.sources_path()}）がないので、読んでいません")
        for msg in report["errors"]:
            self.stdout.write(self.style.WARNING(msg))
        admin_url = os.environ.get("YUIKAORI_ADMIN_URL", "")
        text = updates.summary(report, admin_url)
        self.stdout.write(text)
        self.stdout.write(f"前回から新しい候補: {new_count} 件")
        if dry_run:
            return
        updates.save_report(report)
        if notify_new:
            if not new_count:
                self.stdout.write("新しい候補がないので、LINE には知らせません")
                return
            text = updates.new_summary(report, admin_url)
        if notify or notify_new:
            command = os.environ.get("YUIKAORI_LINE_NOTIFY") or str(Path.home() / ".local/bin/line-notify")
            proc = subprocess.run([command, text], capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                raise CommandError(f"LINE に送れませんでした: {(proc.stderr or proc.stdout).strip()[:300]}")
            self.stdout.write(self.style.SUCCESS("LINE に知らせました"))
