"""管理画面を URL のパス（例: /example）の下で動かすための WSGI ミドルウェア。

リバースプロキシで、ほかのアプリと同じアドレスをパスで分け合うときに使う。
パスを SCRIPT_NAME に入れるので、Django が作るリンク・リダイレクト・静的ファイルの URL にもパスが付く。
プロキシがパスを外して転送しても（/admin/）、付けたまま転送しても（/example/admin/）動くようにする。
"""


class PrefixMiddleware:
    def __init__(self, app, prefix):
        self.app = app
        self.prefix = "/" + prefix.strip("/")

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == self.prefix or path.startswith(self.prefix + "/"):
            path = path[len(self.prefix):]
        environ["SCRIPT_NAME"] = self.prefix
        environ["PATH_INFO"] = path or "/"
        return self.app(environ, start_response)
