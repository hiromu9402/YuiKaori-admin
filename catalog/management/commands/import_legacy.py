from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.importer import import_site
from catalog.models import Live


class Command(BaseCommand):
    help = "公開用の JSON（と旧版の tour.html / my*.html）から DB を作り直す。既存のデータは消える"

    def add_arguments(self, parser):
        parser.add_argument("--site-dir", default=str(settings.SITE_DIR), help="読み込む公開ファイルの場所")
        parser.add_argument("--yes", action="store_true", help="既存のデータがあっても確認せずに作り直す")

    def handle(self, site_dir, yes, **options):
        if Live.objects.exists() and not yes:
            raise CommandError("DB にデータがあります。作り直すときは --yes を付けてください（既存のデータは消えます）")
        warnings = import_site(site_dir)
        for w in warnings:
            self.stdout.write(self.style.WARNING(f"警告: {w}"))
        self.stdout.write(self.style.SUCCESS(f"{site_dir} から取り込みました（警告 {len(warnings)} 件）"))
