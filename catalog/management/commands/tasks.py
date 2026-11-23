from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import Task


def choice(value, choices, name):
    """コード（todo など）か表示名（未着手 など）を、コードにする。"""
    for code, label in choices:
        if str(value) in (str(code), label):
            return code
    raise CommandError(f"{name}が分かりません: {value!r}（{'・'.join(f'{c}={l}' for c, l in choices)}）")


class Command(BaseCommand):
    help = "タスクの一覧・追加・更新・完了をコマンドで行う"

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        p = sub.add_parser("list", help="一覧（既定は完了以外）")
        p.add_argument("--all", action="store_true", help="完了したものも出す")
        p.add_argument("--detail", action="store_true", help="内容・メモも出す")
        p = sub.add_parser("add", help="追加する")
        p.add_argument("title")
        p.add_argument("--category", default="data", help="data / site / ops / other（表示名でもよい）")
        p.add_argument("--priority", default="2", help="1=高 / 2=中 / 3=低（表示名でもよい）")
        p.add_argument("--status", default="todo", help="todo / doing / waiting / hold / done（表示名でもよい）")
        p.add_argument("--detail", default="", help="内容・メモ")
        p = sub.add_parser("update", help="状態・優先度を変え、メモを書き足す")
        p.add_argument("id", type=int)
        p.add_argument("--status")
        p.add_argument("--priority")
        p.add_argument("--note", help="内容・メモの末尾に、日付を付けて書き足す")
        p = sub.add_parser("done", help="完了にする")
        p.add_argument("id", type=int)
        p.add_argument("--note", help="内容・メモの末尾に「【完了】日付：…」として書き足す")

    def handle(self, action, **o):
        getattr(self, f"do_{action}")(**o)

    def show(self, t, detail=False):
        self.stdout.write(f"{t.id:>3}  {t.get_priority_display()}  {t.get_status_display():<6}  "
                          f"{t.get_category_display():<10}  {t.title}")
        if detail and t.detail:
            for line in t.detail.splitlines():
                self.stdout.write(f"       {line}")

    def do_list(self, all, detail, **o):
        tasks = Task.objects.all() if all else Task.objects.exclude(status="done")
        for t in tasks.order_by("priority", "category", "id"):
            self.show(t, detail)
        self.stdout.write(f"{tasks.count()} 件" + ("" if all else f"（完了 {Task.objects.filter(status='done').count()} 件は出していません）"))

    def do_add(self, title, category, priority, status, detail, **o):
        t = Task.objects.create(
            title=title, detail=detail,
            category=choice(category, Task.CATEGORY_CHOICES, "種類"),
            priority=choice(priority, Task.PRIORITY_CHOICES, "優先度"),
            status=choice(status, Task.STATUS_CHOICES, "状態"))
        self.stdout.write(self.style.SUCCESS("追加しました:"))
        self.show(t)

    def get(self, id):
        try:
            return Task.objects.get(pk=id)
        except Task.DoesNotExist:
            raise CommandError(f"タスク {id} がありません")

    def append(self, t, text):
        t.detail = (t.detail + "\n\n" if t.detail else "") + text

    def do_update(self, id, status, priority, note, **o):
        t = self.get(id)
        if not (status or priority or note):
            raise CommandError("--status・--priority・--note のどれかを指定してください")
        if status:
            t.status = choice(status, Task.STATUS_CHOICES, "状態")
        if priority:
            t.priority = choice(priority, Task.PRIORITY_CHOICES, "優先度")
        if note:
            self.append(t, f"{timezone.localdate():%Y/%m/%d}：{note}")
        t.save()
        self.stdout.write(self.style.SUCCESS("更新しました:"))
        self.show(t)

    def do_done(self, id, note, **o):
        t = self.get(id)
        t.status = "done"
        if note:
            self.append(t, f"【完了】{timezone.localdate():%Y/%m/%d}：{note}")
        t.save()
        self.stdout.write(self.style.SUCCESS("完了にしました:"))
        self.show(t)
