"""テストの共通部品。

fixtures/legacy/ には、DB 化する前（ブランチを切った時点）の公開ファイルを保存してある。
これを正解データとして、取り込み→書き出しの往復やフロントの結果を比べる。
"""
import json
from pathlib import Path

from django.test import TestCase

from catalog.importer import import_site

LEGACY_DIR = Path(__file__).resolve().parent / "fixtures" / "legacy"


def load_legacy(name):
    return json.loads((LEGACY_DIR / name).read_text(encoding="utf-8"))


def as_list(value):
    return [] if value in (None, "") else (value if isinstance(value, list) else [value])


def normalize_legacy_live(live):
    """旧版の setlist.json の1件を、書き出しで揃えた型に合わせる（中身は変えない）。"""
    live = dict(live)
    live["setlist"] = as_list(live["setlist"])
    for key in ("encore", "Wencore"):
        if key in live:
            live[key] = as_list(live[key])
            if not live[key]:
                del live[key]
    return live


def normalize_legacy_event(event):
    """旧版の event.json の1件の、月日のゼロ埋め（"03" など）を外す。"""
    event = dict(event)
    for key in ("Year", "Month", "Day"):
        event[key] = str(int(event[key]))
    return event


class LegacyDataTestCase(TestCase):
    """正解データを取り込んだ DB でテストする。取り込みはクラスごとに1回だけ行う。"""

    @classmethod
    def setUpTestData(cls):
        cls.import_warnings = import_site(LEGACY_DIR)
