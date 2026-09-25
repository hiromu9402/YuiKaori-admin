# 作業の引き継ぎメモ（feature/sqlite-admin）

計画の全文: `/home/miyazaki/.claude/plans/async-launching-hejlsberg.md`
（SQLite＋Django 管理画面への移行。ブランチで作業し、テストと受け入れ確認が済んだら `main` にマージする）

## 作業場所
- worktree: `/home/miyazaki/claude/database_yuikaori-dev`（ブランチ `feature/sqlite-admin`）
- 公開中の `main`: `/home/miyazaki/claude/database_yuikaori`（こちらには触れない）
- 仮想環境: `admin/.venv`（`uv venv` と `uv pip install -r requirements.txt` で作り直せる）
- 開発用の DB: `admin/data/db.sqlite3`（git の管理対象外。`manage.py migrate` のあと `manage.py import_legacy --site-dir .. --yes` で作り直せる）

## 済んだこと
1. **段階1〜2（コミット `d431969`）**
   - Django プロジェクトとモデルを作った
   - `import_legacy`、`export_json`、`validate_data` を用意した
   - テスト39件（`manage.py test catalog`）がすべて通る
   - 取り込み→書き出しで、song/CD/setlist は完全に一致した。event は、月がゼロ埋めされた1件（"03"）が "3" になった。このイベントは今のカレンダーに表示されていないので、これはバグの修正になる
2. **段階3の準備（このメモと同じコミット）**
   - 旧版の tour.html では「Step Apple」に `selected` が付いていた。取り込みで読み飛ばしていたので直し、`Tour.compare_default` を追加した
   - その結果 tours.json の形は `{"groups": [...], "default": ...}` になった
   - migration の 0001 は作り直した（まだどこにも適用していないので問題ない）
   - 画面の回帰テスト用に `catalog/tests/e2e/probe.js` と `catalog/tests/e2e/runner.py` を作った
   - 書き換え前の画面の結果を `catalog/tests/fixtures/expected/frontend.json` に保存した。作り直すコマンドは `.venv/bin/python -m catalog.tests.e2e.runner --baseline ..`

## 次にやること（段階3の続き）
1. `common.js` を作る
   - `tours.json` から tour.html の選択肢（optgroup と初期選択）を作る
   - `checklist.json` から my*.html の見出しとチェックボックスを作る。チェックボックスは `<label><input class="checkbox" id=公演ID>表示名</label>` の形にする
2. `tour.html`、`my.html`、`my_c.html`、`my_f.html` の手書き部分を消し、`common.js` を呼ぶ形にする
   - my の3ページは判定処理も共通化し、アーティストは引数で渡す
   - `checkMissingSongs` と `songData` / `setlistData` の名前は残す。probe.js がこれらを参照している
3. 開発用の worktree の直下に `export_json` で書き出す（tours.json と checklist.json も出る）
4. `catalog/tests/test_e2e.py` を作る
   - 流れ：正解データを取り込み → 一時ディレクトリに書き出し → `runner.build_site` と `collect` → `expected/frontend.json` と比べる
   - 期待値との差として許すもの：calendar の events が 1884 から 1885 に増える（ゼロ埋めの修正による）
   - Chromium がない環境では skip する
5. データの疑問点をユーザーに確認する（旧版の my*.html にあったもの）
   - my_c の `2020120501`（5th Anniversary Live -bouquet-）は、正しくは `2023080601` と思われる。今は取り込みで除外している
   - my_c の最初の見出しが「石原夏織 2nd LIVE TOUR -Calm Magic-」になっているが、中身は 2025「As I Am」の公演になっている
   - my（小倉唯）のページに Animelo 2024（`2024083101`）がない
   - my_c に ANIMAX MUSIX 2021/2022（`2021112001`、`2022111901`）がある。しかし setlist の artist は小倉唯だけになっている
   - my_f に ブシロード 2013（`2013032401`）がある。しかし setlist の artist は小倉唯だけになっている
   - tour.html の「Step Apple」に `selected` が付いているのは意図したものか
6. 段階3をコミットする。その後、段階4（admin.py、テキスト一括入力、書き出しアクション、django-axes のテスト）と段階5（serve.py、systemd、README）へ進む

## 注意
- コミットメッセージに Claude の共同作者行とセッションURLは入れない（ユーザーの希望）
- 外部に公開する（tailscale serve / funnel、cloudflared）前には、必ずユーザーに確認する
- このセッションで起動した `http.server`（8765番）と cloudflared のトンネルは、セッションが終わると止まる
