# ゆいかおりデータベース 管理画面

公開サイト [hiromu9402/YuiKaori](https://github.com/hiromu9402/YuiKaori)（https://hiromu9402.github.io/YuiKaori/）のデータを管理する、1人用の管理画面です（Django + SQLite）。
データの元は SQLite で、公開用の JSON（`song.json`・`CD.json`・`setlist.json`・`event.json`・`tours.json`・`checklist.json`）は管理画面から公開サイトのリポジトリに書き出します。

## フォルダーの置き方

```
~/claude/database_yuikaori-admin/   このリポジトリ（管理画面）
~/claude/database_yuikaori/         公開サイトのリポジトリ（hiromu9402/YuiKaori）。JSON の書き出し先
~/claude/database_yuikaori-data/    DB・秘密鍵（git には入れない）
```

公開サイトのリポジトリと DB の場所は、既定ではこのリポジトリの隣です。環境変数 `YUIKAORI_SITE_DIR`・`YUIKAORI_DATA_DIR` で変えられます。

## セットアップ

リポジトリは GitHub で公開しているので、DB と秘密鍵はリポジトリの外（既定は隣の `database_yuikaori-data/`）に置きます。

```bash
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
- **公開前に確かめる**：トップの「公開前のプレビューを開く」で、DB の今の内容のまま、公開サイトと同じページを開けます（`/preview/`。ログインが必要）。ページの HTML・CSS・JS は公開サイトのリポジトリ（`YUIKAORI_SITE_DIR`）のもの、JSON は DB からその場で作ったものです。各ページの上に「プレビュー（未公開）」の帯が出て、フッターの「データ更新」は「未公開」になります。トップと書き出しの画面には、公開中の JSON との違い（増えた・減った・変わった公演・曲・イベントなど）も出ます。公開サイトの作業用フォルダー（`database_yuikaori-dev`。PR のブランチの worktree。`YUIKAORI_PREVIEW_DEV_DIR` で変えられる）があるときは、「作業中のブランチのプレビュー」（`/preview/dev/`）で、マージ前のページの変更も含めて確かめられます。帯のリンクで、公開中のページ（main）と切り替えられます。

コマンドでも同じことができます。

```bash
.venv/bin/python manage.py validate_data    # 整合性チェック
.venv/bin/python manage.py export_json      # チェックしてから書き出す
```

## 作業用のコマンド

データを直すときや、確認するときによく使うものです（`.venv/bin/python manage.py …`）。

| コマンド | すること |
|---|---|
| `backup_db --label <名前>` | DB を保存先の `backup/` に写す（`db-日時-名前.sqlite3`）。サービスが動いている最中でも壊れない方法で写す。データを直す前に使う |
| `export_json --check` | 書き出さずに、今の公開ファイルから何が変わるかを表示する（追加・削除・変更された公演・曲・イベントなど） |
| `record_verify <CSV>` | 公演の照合の記録（状態・照合日・出典・メモ）を CSV からまとめて書き込む。`--apply` を付けないと差分の表示だけ。1行でも誤りがあると何も書き込まない |
| `check_updates` | データ更新の候補を集めて、管理画面のトップに出す（下の「データ更新の候補」） |
| `tasks list` / `add` / `update` / `done` | タスクの一覧（`--all` で完了も）・追加・更新（状態・優先度・メモの追記）・完了 |

### データ更新の候補（毎週月曜）

`manage.py check_updates` は、次の 3 つを集めて保存先の `update_report.json` に書き、管理画面のトップの「データ更新の候補」に出します。`--notify` を付けると LINE にも知らせます（`--notify-new` なら、前回から新しい候補が増えたときだけ、増えた分を知らせます。管理画面のトップでは、増えたものに「新」の印が付きます）（`YUIKAORI_LINE_NOTIFY` のコマンド。既定は `~/.local/bin/line-notify`。本文に付ける管理画面の URL は `YUIKAORI_ADMIN_URL`）。

1. 外部のイベント一覧（出演者ごとのイベントのページ）にあって、DB にないイベント（60 日前から先の予定まで。同じ日付で題名が似ているものは登録済みとみなす）
2. 開催日を過ぎたのに、セットリストがないライブ（1 年前まで。フェス・合同ライブも含む）
3. これから 1 か月のライブ・ファンクラブイベント（終わったらセットリストを足す）

1 の読み先（一覧の URL・出演者の番号・ページから取り出す正規表現）は、保存先の `update_sources.json` に書きます（リポジトリには入れません。書き方は `catalog/updates.py` の説明）。ないときは 1 を飛ばします。外部のサイトは 1 人あたり数ページだけを、2 秒ずつ間をあけて読みます。`--dry-run` で、保存も通知もせずに結果だけを見られます。毎週月曜に cron で実行します。

```cron
0 9 * * 1 cd ~/claude/database_yuikaori-admin && .venv/bin/python manage.py check_updates --notify-new >> ~/claude/database_yuikaori-data/check_updates.log 2>&1
```

`record_verify` の CSV（UTF-8、1行目は見出し）:

```csv
live_id,status,date,source,note
2025112401,一致,2026-11-24,https://example.com/report | 公式 X の投稿,アンコールの曲順も一致
```

- `status` は `ok`・`fixed`・`partial`・`doubt`・`notfound` か、表示名（一致・修正済み など）。`date` が空なら今日。
- `source` は「 | 」で区切ると、1行に1つずつ入る。`source`・`note` が空なら今の値のまま。

### 画面の確認用サーバー

```bash
.venv/bin/python tools/preview_server.py          # http://127.0.0.1:8766/
```

本番の DB の写しを一時ディレクトリに作り、ログインした状態の管理画面を開きます（画面写真や見た目の確認用）。本番の DB と秘密鍵には書き込みません。ログインを省くので 127.0.0.1 でしか待ち受けず、止めると（Ctrl-C でも kill でも）写しは消えます。

## データ

隣の `database_yuikaori-data/` に保存されます。環境変数 `YUIKAORI_DATA_DIR` で変えられます（テストは使い捨てのディレクトリを使います）。書き出し先は `YUIKAORI_SITE_DIR` で変えられます（既定は隣の `database_yuikaori/`）。

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
- `catalog/tests/fixtures/expected/frontend.json` は、DB 化する前の公開ページの表示結果（披露回数・未回収数・比較表など）です。書き出した JSON と、公開サイトのリポジトリにある今の HTML で同じ結果になることを、headless Chromium で確かめます（公開サイトのリポジトリがないときは飛ばします）。

## 公開サイトの配信

公開サイトは、公開サイトのリポジトリ（hiromu9402/YuiKaori）の GitHub Pages で公開しています。公開するファイルの許可リストや Actions の設定は、そちらのリポジトリにあります。

管理画面で書き出したら、公開サイトのリポジトリで JSON の差分を確かめて commit・push します。
