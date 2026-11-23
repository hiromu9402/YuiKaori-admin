"""画面写真や見た目の確認のための管理画面（本番 DB の写しを使い、ログインを省く）。

    .venv/bin/python tools/preview_server.py              # http://127.0.0.1:8766/ で開く
    .venv/bin/python tools/preview_server.py --port 8767 --user <ユーザー名>

- 本番の保存先（YUIKAORI_DATA_DIR。既定は隣の database_yuikaori-data/）の DB を一時ディレクトリに写して使う。
  本番の DB と秘密鍵には書き込まない（秘密鍵は、写しの側で新しく作る）。
- 写しの DB にログインした状態のセッションを作り、すべてのリクエストにその Cookie を付ける。
  ログインを省くので、127.0.0.1 でしか待ち受けない。止めると（Ctrl-C でも kill でも）一時ディレクトリは消える。
"""
import argparse
import os
import signal
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def source_data_dir():
    return Path(os.environ.get("YUIKAORI_DATA_DIR") or REPO_DIR.parent / "database_yuikaori-data")


def copy_data(src_dir, dest_dir):
    """src_dir の DB を dest_dir に写し、collectstatic の出力を参照できるようにする。src_dir には書き込まない。"""
    src_dir, dest_dir = Path(src_dir), Path(dest_dir)
    src_db = src_dir / "db.sqlite3"
    if not src_db.exists():
        raise SystemExit(f"DB がありません: {src_db}")
    with sqlite3.connect(f"file:{src_db}?mode=ro", uri=True, timeout=30) as a, sqlite3.connect(dest_dir / "db.sqlite3") as b:
        a.backup(b)
    (dest_dir / "db.sqlite3").chmod(0o600)
    # データ更新の候補（check_updates の結果）があれば、トップに出るように写す
    if (src_dir / "update_report.json").is_file():
        (dest_dir / "update_report.json").write_bytes((src_dir / "update_report.json").read_bytes())
    if (src_dir / "static").is_dir():
        (dest_dir / "static").symlink_to(src_dir / "static")


def check_host(host):
    if host not in LOCAL_HOSTS:
        raise SystemExit(f"ログインを省く確認用なので、127.0.0.1 か localhost でしか待ち受けません（指定: {host}）")


def login_session(username=None):
    """写しの DB に、ログインした状態のセッションを作って、そのキーを返す（django.setup() のあとで呼ぶ）。"""
    from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
    from django.contrib.sessions.backends.db import SessionStore

    users = get_user_model().objects.filter(is_active=True, is_superuser=True)
    user = users.get(username=username) if username else users.order_by("pk").first()
    if user is None:
        raise SystemExit("ログインに使う管理者のユーザーがいません")
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.create()
    return session.session_key


def with_session(app, cookie_name, key):
    def wrapped(environ, start_response):
        environ["HTTP_COOKIE"] = f"{cookie_name}={key}"
        return app(environ, start_response)
    return wrapped


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--user", help="ログインした状態にするユーザー（既定は最初の管理者）")
    args = parser.parse_args()
    check_host(args.host)
    # kill（SIGTERM）で止めたときも、一時ディレクトリ（DB の写し）を消してから終わる
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    with tempfile.TemporaryDirectory(prefix="yuikaori-preview-") as tmp:
        copy_data(source_data_dir(), tmp)
        # 以降の Django はすべて写しを使う（本番の保存先は読まない）
        os.environ["YUIKAORI_DATA_DIR"] = tmp
        os.environ.pop("YUIKAORI_URL_PREFIX", None)
        os.environ.pop("YUIKAORI_COOKIE_SECURE", None)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        sys.path.insert(0, str(REPO_DIR))
        import django
        django.setup()
        from django.conf import settings
        from django.core.wsgi import get_wsgi_application
        from waitress import serve

        key = login_session(args.user)
        print(f"確認用の管理画面（本番 DB の写し・ログイン済み）: http://{args.host}:{args.port}/", flush=True)
        serve(with_session(get_wsgi_application(), settings.SESSION_COOKIE_NAME, key), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
