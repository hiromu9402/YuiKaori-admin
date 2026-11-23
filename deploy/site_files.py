"""公開サイトに含めるファイルの許可リスト。

serve_site.py（手元での確認用の配信）と build_site.py（GitHub Pages に載せるファイルの収集）で共通に使う。
リポジトリ直下の .html / .css / .js / .json と、sub/ の .html だけを公開する。
.git/、admin/（管理画面のソース）、.github/、README.md、HANDOFF.md などの作業用ファイルは含めない。
"""
import re
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parents[2]  # admin/deploy/ → リポジトリの直下

# 公開してよいパス（リポジトリ直下からの相対パス）
ALLOWED = [
    re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(html|css|js|json)$"),
    re.compile(r"^sub/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.html$"),
]


def allowed(relpath):
    return any(p.match(relpath) for p in ALLOWED)


def public_files(site_dir=SITE_DIR):
    """公開するファイルの相対パスを、名前順に返す。"""
    site_dir = Path(site_dir)
    candidates = [p for p in site_dir.iterdir() if p.is_file()]
    if (site_dir / "sub").is_dir():
        candidates += [p for p in (site_dir / "sub").iterdir() if p.is_file()]
    paths = (p.relative_to(site_dir).as_posix() for p in candidates)
    return sorted(p for p in paths if allowed(p))
