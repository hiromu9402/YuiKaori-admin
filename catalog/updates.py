"""データ更新の候補を集める（manage.py check_updates）。

毎月 1 日に cron で実行し、次の 3 つを update_report.json（保存先）にまとめる。管理画面のトップに表示し、LINE にも知らせる。
1. 外部のイベント一覧（出演者ごとのイベントのページ）にあって、DB にないイベント（これから・最近のもの）
2. 開催日を過ぎたのに、セットリストがないライブ（フェス・合同ライブも含む）
3. これから 1 か月のライブ・ファンクラブイベント（終わったらセットリストを足す）

1 の読み先は、保存先の update_sources.json に書く（リポジトリには入れない）。ないときは 1 を飛ばす。
  {
    "name": "表示名",
    "list_url": "https://…/{actor_id}/…?page={page}",   出演者ごとのイベント一覧（新しい順）の URL
    "event_url": "https://…/{id}",                        イベントのページの URL
    "actors": {"小倉唯": 1, "石原夏織": 2, "ゆいかおり": 3},  出演者の番号
    "patterns": {                                          一覧のページから取り出す正規表現
      "item": "…",   1 件ずつに分ける区切り（re.split。最初の部分は捨てる）
      "date": "…",   日付（年・月・日の 3 グループ）
      "link": "…",   イベントの番号と題名（2 グループ）
      "venue": "…",  会場（1 グループ。なくてもよい）
      "actor": "…"   出演者（1 グループ。findall。なくてもよい）
    }
  }
読むのは 1 人あたり数ページだけにし、ページの間は少し待つ。
"""
import difflib
import html
import json
import os
import re
import tempfile
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings

from .models import Event

USER_AGENT = "Mozilla/5.0 (X11; Linux aarch64) YuiKaoriDB-update-check"
LOOKBACK_DAYS = 60      # 外部の一覧は、この日数より前のイベントまでは見ない
MAX_PAGES = 8           # 1 人あたりに読むページ数の上限
WAIT_SECONDS = 2        # ページを読む間隔
SETLIST_DAYS = 365      # セットリストがないライブを、この日数前まで探す
UPCOMING_DAYS = 31
LIVE_CLASSES = ["ライブ", "ファンクラブイベント"]
DEFAULT_SOURCE_NAME = "外部のイベント一覧"


def today():
    return date.today()


def report_path():
    return Path(settings.DATA_DIR) / "update_report.json"


def sources_path():
    return Path(settings.DATA_DIR) / "update_sources.json"


def load_report():
    try:
        return json.loads(report_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_report(report):
    path = report_path()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".update_report.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_source():
    """update_sources.json を読む。ないときは None。"""
    try:
        source = json.loads(sources_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    for key in ("list_url", "event_url", "actors", "patterns"):
        if key not in source:
            raise ValueError(f"{sources_path()} に {key} がありません")
    return source


# ---------- 外部のイベント一覧 ----------

def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", "replace")


def parse_events(page_html, patterns):
    """イベント一覧のページから、[{id, date, title, venue, actors}] を取り出す。"""
    events = []
    for block in re.split(patterns["item"], page_html)[1:]:
        day = re.search(patterns["date"], block)
        link = re.search(patterns["link"], block, re.S)
        if not (day and link):
            continue
        venue = re.search(patterns["venue"], block, re.S) if patterns.get("venue") else None
        actors = re.findall(patterns["actor"], block) if patterns.get("actor") else []
        events.append({
            "id": link.group(1),
            "date": date(*map(int, day.groups())).isoformat(),
            "title": html.unescape(re.sub(r"<[^>]+>", "", link.group(2))).strip(),
            "venue": html.unescape(re.sub(r"<[^>]+>", "", venue.group(1))).strip() if venue else "",
            "actors": [html.unescape(a).strip() for a in actors],
        })
    return events


def fetch_recent(source, today, fetch=None, wait=None):
    """出演者ごとのイベント一覧を新しいほうから読み、LOOKBACK_DAYS 日前までのイベントを返す（同じイベントは 1 件にする）。"""
    # 既定値は呼んだ時点のものを使う（テストで差し替えられるように）
    fetch = fetch or fetch_page
    wait = WAIT_SECONDS if wait is None else wait
    oldest = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    found, errors = {}, []
    first = True
    for name, actor_id in source["actors"].items():
        for page in range(1, MAX_PAGES + 1):
            if not first and wait:
                time.sleep(wait)
            first = False
            try:
                events = parse_events(fetch(source["list_url"].format(actor_id=actor_id, page=page)), source["patterns"])
            except Exception as e:  # noqa: BLE001  通信の失敗は、ほかの人の分を続けるために記録だけする
                errors.append(f"{name} の {page} ページ目を読めませんでした: {e}")
                break
            for e in events:
                if e["date"] >= oldest:
                    found.setdefault(e["id"], e)
            if not events or events[-1]["date"] < oldest:
                break
    return sorted(found.values(), key=lambda e: (e["date"], e["title"])), errors


# ---------- DB との突き合わせ ----------

def normalize(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[\s\"'“”‘’「」『』【】\[\]（）()<>＜＞〈〉《》〜~\-‐－―・･:：!！?？&＆♡♥♪☆★…,，.。、/／#＃@＠]", "", text)


def same_event(a, b):
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return False
    return a == b or a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def missing_events(found):
    """DB に同じ日付・似た題名のイベントがないものを返す。"""
    dates = {date.fromisoformat(e["date"]) for e in found}
    by_date = {}
    for ev in Event.objects.filter(date__in=dates):
        by_date.setdefault(ev.date.isoformat(), []).append(f"{ev.title} {ev.title2}")
    return [e for e in found if not any(same_event(e["title"], t) for t in by_date.get(e["date"], []))]


def event_row(ev):
    return {"pk": ev.pk, "date": ev.date.isoformat(), "class1": ev.class1, "title": ev.title,
            "artists": [a.name for a in ev.artists.all()]}


def build_report(today=None, fetch=None, wait=None, source=None):
    today = today or globals()["today"]()
    source = source if source is not None else load_source()
    new, errors, checked = [], [], 0
    if source:
        found, errors = fetch_recent(source, today, fetch=fetch, wait=wait)
        checked = len(found)
        new = [{**e, "url": source["event_url"].format(id=e["id"])} for e in missing_events(found)]
    no_setlist = (Event.objects.filter(class1="ライブ", live__isnull=True, date__lt=today,
                                       date__gte=today - timedelta(days=SETLIST_DAYS))
                  .prefetch_related("artists").order_by("-date", "sort"))
    upcoming = (Event.objects.filter(class1__in=LIVE_CLASSES, date__gte=today,
                                     date__lte=today + timedelta(days=UPCOMING_DAYS))
                .prefetch_related("artists").order_by("date", "sort"))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "source_name": (source or {}).get("name") or DEFAULT_SOURCE_NAME,
        "source_enabled": bool(source),
        "checked": checked,
        "new_events": new,
        "missing_setlists": [event_row(e) for e in no_setlist],
        "upcoming": [event_row(e) for e in upcoming],
        "errors": errors,
    }


def summary(report, admin_url=""):
    """LINE で送る本文。"""
    lines = [f"ゆいかおりDB の更新の候補（{report['today']}）"]
    if report.get("source_enabled"):
        lines.append(f"・{report['source_name']}にあって DB にないイベント: {len(report['new_events'])} 件")
    lines += [f"・セットリストがない過去のライブ: {len(report['missing_setlists'])} 件",
              f"・これから 1 か月のライブ: {len(report['upcoming'])} 件"]
    if report["errors"]:
        lines.append(f"・読めなかったページ: {len(report['errors'])} 件")
    lines.append("詳しくは管理画面のトップを見てください。" + (f"\n{admin_url}" if admin_url else ""))
    return "\n".join(lines)
