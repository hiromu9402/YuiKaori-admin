"""ゆいかおりデータベース管理画面の設定。

データ（SQLite・秘密鍵・collectstatic の出力）は、リポジトリの外の、隣のフォルダー（database_yuikaori-data/）に置く。
公開サイトのリポジトリ（hiromu9402/YuiKaori）は、隣の database_yuikaori/ にある前提で、公開 JSON をそこに書き出す。
環境変数 YUIKAORI_DATA_DIR で保存先を、YUIKAORI_SITE_DIR で公開 JSON の書き出し先を変えられる。
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# リポジトリは GitHub で公開しているので、DB と秘密鍵は既定でもリポジトリの外（隣のフォルダー）に置く
# 例: ~/claude/database_yuikaori-admin（このリポジトリ）→ ~/claude/database_yuikaori-data
DATA_DIR = Path(os.environ.get("YUIKAORI_DATA_DIR") or BASE_DIR.parent / "database_yuikaori-data")
# 公開サイトのリポジトリ（song.json などを書き出す場所）。既定は隣の database_yuikaori/
SITE_DIR = Path(os.environ.get("YUIKAORI_SITE_DIR") or BASE_DIR.parent / "database_yuikaori")


def load_secret_key():
    """data/secret_key を読む。なければ作る（所有者だけが読める 0600）。"""
    path = DATA_DIR / "secret_key"
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        key = secrets.token_urlsafe(50)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        return key


SECRET_KEY = load_secret_key()
DEBUG = os.environ.get("YUIKAORI_DEBUG") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("YUIKAORI_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]
# HTTPS のリバースプロキシ経由で使うときは、そのオリジンを指定する（例: https://admin.example.com）
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("YUIKAORI_CSRF_TRUSTED_ORIGINS", "").split(",") if o]
# リバースプロキシで、同じアドレスをほかのアプリとパスで分け合うことがあるので、
# Cookie は管理画面専用の名前にし、管理画面のパスの下だけで送られるようにする
SESSION_COOKIE_NAME = "yuikaori_sessionid"
CSRF_COOKIE_NAME = "yuikaori_csrftoken"
URL_PREFIX = "/" + os.environ.get("YUIKAORI_URL_PREFIX", "").strip("/")
SESSION_COOKIE_PATH = CSRF_COOKIE_PATH = URL_PREFIX.rstrip("/") + "/"
if os.environ.get("YUIKAORI_COOKIE_SECURE") == "1":
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "catalog.admin_apps.YuikaoriAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # 認証の失敗を数えてロックする。最後に置く（django-axes の指定）
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # 時間（15分）
AXES_LOCKOUT_PARAMETERS = ["ip_address", ["username", "user_agent"]]
AXES_RESET_ON_SUCCESS = True
# 接続元 IP は REMOTE_ADDR だけを使う。プロキシ経由のときは serve.py（waitress）が
# 127.0.0.1 からの X-Forwarded-For だけを信頼して REMOTE_ADDR に入れるので、偽装された値は使われない
AXES_IPWARE_META_PRECEDENCE_ORDER = ["REMOTE_ADDR"]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

# パスの下で動かすときも CSS/JS の URL にパスが付くよう、絶対パスで指定する
STATIC_URL = URL_PREFIX.rstrip("/") + "/static/"
STATIC_ROOT = DATA_DIR / "static"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
