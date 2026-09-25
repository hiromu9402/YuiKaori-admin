from django.core.management.base import BaseCommand, CommandError

from catalog.validate import validate


class Command(BaseCommand):
    help = "データの整合性をチェックする"

    def add_arguments(self, parser):
        parser.add_argument("--quiet-warnings", action="store_true", help="警告を表示しない")

    def handle(self, quiet_warnings, **options):
        errors, warnings = validate()
        if not quiet_warnings:
            for w in warnings:
                self.stdout.write(self.style.WARNING(f"警告: {w}"))
        for e in errors:
            self.stdout.write(self.style.ERROR(f"エラー: {e}"))
        if errors:
            raise CommandError(f"エラーが {len(errors)} 件あります")
        self.stdout.write(self.style.SUCCESS(f"エラーはありません（警告 {len(warnings)} 件）"))
