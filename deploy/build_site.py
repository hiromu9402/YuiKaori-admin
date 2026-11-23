"""公開サイトのファイルだけを出力先に集める（GitHub Pages で公開する内容）。

許可リスト（site_files.py）に合うファイルだけをコピーする。GitHub Actions（.github/workflows/pages.yml）で使うほか、
公開される内容を手元で確かめるときにも使う。

    python3 admin/deploy/build_site.py _site
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_files import SITE_DIR, public_files  # noqa: E402


def build(out_dir, site_dir=SITE_DIR):
    """out_dir に公開ファイルをコピーし、コピーしたファイルの相対パスを返す。out_dir は空か、まだないこと。"""
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"出力先が空ではありません: {out_dir}")
    files = public_files(site_dir)
    for rel in files:
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(site_dir) / rel, dest)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", help="出力先のディレクトリ（空か、まだないこと）")
    args = parser.parse_args()
    files = build(args.out_dir)
    print(f"{len(files)} 個のファイルを {args.out_dir} に書き出しました")


if __name__ == "__main__":
    main()
