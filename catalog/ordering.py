"""書き出しの並び順（sort）を決める。

公演とイベントは日付の新しい順、曲と CD は末尾に追加していく（旧版の JSON と同じ並べ方）。
取り込み時の sort は 1000 刻みなので、間に入れる余地がなくなったときだけ全体を振り直す。
"""
from django.db import transaction
from django.db.models import Max

from .importer import SORT_STEP


def next_sort(model):
    return (model.objects.aggregate(v=Max("sort"))["v"] or 0) + SORT_STEP


@transaction.atomic
def place_by_date_desc(obj):
    """obj（date と sort を持つ、保存済みのモデル）を、日付の新しい順の正しい位置に置く。

    同じ日付のものがあれば、その最後（既存のものの後ろ）に置く。
    """
    model = type(obj)
    others = list(model.objects.exclude(pk=obj.pk).order_by("sort", "pk").values_list("pk", "sort", "date"))
    index = next((i for i, (_, _, d) in enumerate(others) if d < obj.date), len(others))
    before = others[index - 1][1] if index > 0 else None
    after = others[index][1] if index < len(others) else None
    if before is None and after is None:
        sort = 0
    elif before is None:
        sort = after - SORT_STEP
    elif after is None:
        sort = before + SORT_STEP
    elif after - before >= 2:
        sort = (before + after) // 2
    else:
        # 間に余地がないので、全体を 1000 刻みで振り直す
        order = [pk for pk, _, _ in others]
        order.insert(index, obj.pk)
        for i, pk in enumerate(order):
            model.objects.filter(pk=pk).update(sort=i * SORT_STEP)
        obj.sort = index * SORT_STEP
        return
    model.objects.filter(pk=obj.pk).update(sort=sort)
    obj.sort = sort
