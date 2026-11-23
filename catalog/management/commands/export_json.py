from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.export_diff import changes
from catalog.exporter import write_all
from catalog.validate import validate


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
        found = changes(site_dir)
        for c in found:
            self.stdout.write(f"{c['name']}:")
            for line in c["lines"]:
                self.stdout.write(f"  {line}")
        names = ", ".join(c["name"] for c in found) or "なし"
        self.stdout.write(self.style.SUCCESS(f"変わるファイル: {names}（警告 {warnings} 件。書き出してはいません）"))
