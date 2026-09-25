from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.exporter import write_all
from catalog.validate import validate


class Command(BaseCommand):
    help = "整合性をチェックしてから、公開用の JSON を書き出す"

    def add_arguments(self, parser):
        parser.add_argument("--site-dir", default=str(settings.SITE_DIR), help="書き出し先")

    def handle(self, site_dir, **options):
        errors, warnings = validate()
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"エラー: {e}"))
            raise CommandError(f"エラーが {len(errors)} 件あるので書き出しませんでした")
        changed = write_all(site_dir)
        self.stdout.write(self.style.SUCCESS(
            f"{site_dir} に書き出しました。変更: {', '.join(changed) if changed else 'なし'}（警告 {len(warnings)} 件）"))
