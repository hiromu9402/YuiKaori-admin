# ゆいかおりデータベース 管理画面

公開サイト（リポジトリの直下にある `index.html` など）のデータを管理する、1人用の管理画面です（Django + SQLite）。
データの元は SQLite で、公開用の JSON（`song.json`・`CD.json`・`setlist.json`・`event.json`・`tours.json`・`checklist.json`）は管理画面から書き出します。

## セットアップ

リポジトリは GitHub で公開しているので、DB と秘密鍵はリポジトリの外（既定は `~/.local/share/yuikaori-admin`）に置きます。

```bash
cd admin
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py import_legacy        # 今の公開 JSON から DB を作る（初回だけ）
.venv/bin/python manage.py createsuperuser      # ログインするユーザーを作る
.venv/bin/python manage.py collectstatic --noinput
```

## 起動

```bash
.venv/bin/python serve.py      # 127.0.0.1:8002 で待ち受ける
```

常駐させる場合は systemd のユーザーサービスとして登録します（`deploy/yuikaori-admin.service`）。

```bash
cp deploy/yuikaori-admin.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now yuikaori-admin
```

`127.0.0.1` だけで待ち受けます。ほかの端末から使うときは、HTTPS のリバースプロキシ経由にしてください。その場合は、サービスファイルのコメントにある環境変数を設定します。実際のホスト名やパスはリポジトリに書かず、systemd の drop-in（`~/.config/systemd/user/yuikaori-admin.service.d/*.conf`）で渡します。

```ini
[Service]
Environment=YUIKAORI_URL_PREFIX=/<パス>          # パスの下で動かすときだけ
Environment=YUIKAORI_COOKIE_SECURE=1
Environment=YUIKAORI_ALLOWED_HOSTS=127.0.0.1,localhost,<ホスト名>
Environment=YUIKAORI_CSRF_TRUSTED_ORIGINS=https://<ホスト名>[:<ポート>]
```

- `YUIKAORI_URL_PREFIX` を指定すると、リンク・リダイレクト・CSS の URL にそのパスが付きます。プロキシがパスを外して転送しても、付けたまま転送しても動きます。
- Cookie は管理画面専用の名前（`yuikaori_sessionid`・`yuikaori_csrftoken`）で、管理画面のパスの下だけに送られます。同じアドレスのほかのアプリとはぶつかりません。
- インターネットから開ける場所に置くときは、パスワードを長いものにしてください（`.venv/bin/python manage.py changepassword <ユーザー名>`）。ログイン画面以外は、ログインしないと見えません。
ログインに5回続けて失敗すると、その接続元は15分間ロックされます（django-axes）。ロックを解除するときは `.venv/bin/python manage.py axes_reset` を実行します。

## 使い方

- **公演を追加する**：「公演」→「公演を追加」で開催日・公演名・会場・出演を入れて保存します。公演ID は空のままなら開催日から自動で決まります。保存するとセットリストの一括入力に進みます。
- **セットリストの一括入力**：1行に1曲。メドレーは `[メドレー] 曲A / 曲B`、区分は `== アンコール`・`== Wアンコール` の行で切り替えます。登録されていない曲名があると、表記ゆれの候補を出すので、別表記として登録するか新しい曲として登録するかを選びます。
- **イベントを作る**：公演を追加するとき「対応するイベントも作る」（最初からオン）にしておくと、日付・公演名・会場・出演を引き継いだイベントも一緒に作ります。あとから作るときは、公演の一覧で公演を選び、操作から「選んだ公演からイベントを作る」を実行します。分類や開始時刻はイベントの画面で追記します。
- **未回収楽曲チェックに載せる**：公演の画面の下にある「未回収チェックでの表示」で、見出しと表示名を追加します。新しい見出しは「未回収チェックの見出し」から作ります。
- **ツアー比較ページに載せる**：「ツアー・シリーズ」で「比較ページのグループ」を設定します。
- **公開する**：トップページの「公開ファイルの書き出しへ」から書き出します。整合性チェックでエラーがあると書き出しません。書き出したら、リポジトリで差分を確認してコミットします。

コマンドでも同じことができます。

```bash
.venv/bin/python manage.py validate_data    # 整合性チェック
.venv/bin/python manage.py export_json      # チェックしてから書き出す
```

## データ

`~/.local/share/yuikaori-admin` に保存されます。環境変数 `YUIKAORI_DATA_DIR` で変えられます（テストは使い捨てのディレクトリを使います）。書き出し先は `YUIKAORI_SITE_DIR` で変えられます（既定はリポジトリの直下）。

| ファイル | 内容 |
|---|---|
| `db.sqlite3` | データと管理画面のユーザー |
| `secret_key` | セッションの署名鍵（初回に自動で作る） |
| `static/` | collectstatic で集めた管理画面の CSS/JS |

DB を失っても、書き出した JSON から `import_legacy --yes` で作り直せます（ユーザーと別表記は作り直せないので、DB のバックアップも取ってください）。

## テスト

```bash
tests/run_all.sh          # すべて
tests/run_all.sh unit     # 画面（Chromium）以外
tests/run_all.sh e2e      # 公開ページの回帰テスト（headless Chromium）
```

- `catalog/tests/fixtures/legacy/` には、DB 化する前の公開ファイルを保存しています。取り込み→書き出しの往復で、これと中身が一致することを確かめます。
- `catalog/tests/fixtures/expected/frontend.json` は、DB 化する前の公開ページの表示結果（披露回数・未回収数・比較表など）です。書き出した JSON と今の HTML で同じ結果になることを、headless Chromium で確かめます。

## 公開サイトの配信

公開サイトは GitHub Pages で公開する（`.github/workflows/pages.yml`）。`main` に push すると、Actions が `admin/deploy/build_site.py` で公開ファイルだけを集めて公開する。

公開するファイルは `admin/deploy/site_files.py` の許可リストで決める。リポジトリ直下の `.html` / `.css` / `.js` / `.json` と `sub/` のページだけで、`.git/`、`admin/`、`.github/`、`README.md`、`HANDOFF.md` などは含めない。

    python3 admin/deploy/build_site.py /tmp/site    # 公開される内容を手元で確かめる

手元で確かめるときは `admin/deploy/serve_site.py` で配信する（127.0.0.1:8765、同じ許可リストを使う）。`python3 -m http.server` でリポジトリをそのまま配信すると、許可リスト以外のファイルも外から見えてしまうので使わない。

    python3 admin/deploy/serve_site.py            # 127.0.0.1:8765
