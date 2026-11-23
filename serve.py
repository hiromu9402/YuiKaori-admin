"""本番用の起動スクリプト（waitress）。

    .venv/bin/python serve.py

127.0.0.1 だけで待ち受ける。リバースプロキシのパスの下で使うときは YUIKAORI_URL_PREFIX（例: /example）を指定する。
リバースプロキシ（127.0.0.1 から接続）経由で使うときは、
プロキシが付ける X-Forwarded-For を waitress が接続元 IP として扱うので、django-axes のロックが接続元ごとに効く。
"""
import os

from waitress import serve

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application  # noqa: E402  YUIKAORI_URL_PREFIX の指定もここで反映する

if __name__ == "__main__":
    serve(
        application,
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8002")),
        trusted_proxy="127.0.0.1",
        trusted_proxy_count=1,
        trusted_proxy_headers={"x-forwarded-for"},
        clear_untrusted_proxy_headers=True,
    )
