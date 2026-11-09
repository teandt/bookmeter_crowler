# テスト方針
`cr_bookmeter/bookmeter_crawl.py`、Web UI、設定、Spider、Pipelineのテスト構成と実行方法を示す。
保存済みHTMLを使うテストでは、`test/testdata` のデータを利用する。
テストデータの取得方法は [get_testdata_spec.md](get_testdata_spec.md) を参照する。

# テストコード実行環境
`bookmeter_crawl.py` と同様に、リポジトリの `venv` 仮想環境下で実行する。
実行コマンドはリポジトリのルートディレクトリを基準とする。

# テストコード構成

## 基本方針
`cr_bookmeter/bookmeter_crawl.py` は、HTML解析そのものではなく、DB操作、CSV出力、Scrapy起動順制御、CLI分岐を担当するオーケストレーション層である。  
そのため、保存済みHTMLを使うSpider解析テストと、`bookmeter_crawl.py` のDB・制御ロジックのテストを分けて作成する。

実ネットワークへのアクセスは行わない。  
`test/testdata/url_map.json` と `test/testdata/page/**/*.html` を利用し、Scrapyの `HtmlResponse` をテストコード側で生成してSpiderの `parse()` を直接検証する。

本番DB `cr_bookmeter/sqlite/bookmeter.db` はテストで直接使用しない。  
DB操作のテストでは、pytest fixtureで一時SQLite DBを作成し、`bookmeter_crawl.Session` をmonkeypatchする。

ただし、現在の `conftest.py` の `db_session_factory` は `Session` だけを差し替え、`bookmeter_crawl.engine` と `_db_path` は差し替えていない。
Web UIの一部テストは `initialize_database()` を呼ぶため、そのまま実行すると本番DBに対して `Base.metadata.create_all(engine)` が実行され、不足テーブルが追加される可能性がある。
本番DBを使用しない方針を満たすには、fixture側の隔離対応が必要である。
対応するまでは、後述の「一時DBでの実行手順」で初期化処理の接続先も一時DBに切り替える。

## ファイル構成

```text
test/
  conftest.py
  test_spiders_from_testdata.py
  test_bookmeter_crawl_db.py
  test_bookmeter_crawl_export_search.py
  test_bookmeter_crawl_runner.py
  test_bookmeter_crawl_cli.py
  test_bookmeter_web.py
  test_config.py
  test_crawl_results.py
  test_pipeline_staging.py
```

## 各テストファイルの役割

### `conftest.py`
テスト共通のfixtureを定義する。

- 一時SQLite DBを作成するfixture
- `bookmeter_crawl.Session` をテスト用DBへ差し替えるfixture
- `test/testdata/url_map.json` を読み込むfixture
- ローカルHTMLから `HtmlResponse` を生成するヘルパーfixture
- 必要に応じて `sys.path` やカレントディレクトリを調整するfixture
- 全HTMLを対象にするテストのHTML件数・アイテム件数を集計し、終了時に表示するフック

`db_session_factory` による接続先の差し替え範囲は、基本方針に記載した制約に注意する。

### `test_spiders_from_testdata.py`
保存済みHTMLを使ってSpiderのHTML解析を検証する。

対象:

- `BookmeterReadSpider.parse()`
- `BookmeterStackedSpider.parse()`
- `BookmeterBookDetailSpider.parse()`

主な検証内容:

- 読んだ本リストから `id`, `short_title`, `authors`, `date`, `url` が取得できる
- 積読本リストから `id`, `short_title`, `authors`, `date`, `url` が取得できる
- リストページに著者情報がない場合、`authors` は `None` になることを許容する
- 書籍詳細ページから `id`, `title`, `pages`, `amazon_url` が取得できる
- 詳細ページの外部リンクが対応するAmazon `/dp/` 形式の場合は `asin` を取得し、それ以外の形式では `asin` が設定されないことを許容する
- 次ページリンクがあるリストページでは、次ページへの `Request` がyieldされる

代表的なHTMLを使うテストと、保存済みHTMLを全件解析するテストがある。
ファイル全体に `pytestmark = pytest.mark.slow` が設定されているため、代表例を含むすべてのテストが `slow` の対象となる。
`-m slow` ではこのファイル全体を実行し、`-m "not slow"` ではこのファイル全体を除外する。
保存済みHTMLと `url_map.json` はGit管理対象外のため、別途用意する必要がある。テスト実行中にデータを取得することはない。

### `test_bookmeter_crawl_db.py`
`bookmeter_crawl.py` のDB操作ロジックを一時DBで検証する。

対象:

- `get_urls_for_detail_crawl()`
- `handle_delete_details()`
- `handle_db_checks()`
- `initialize_database()`
- `session_scope()`

主な検証内容:

- 読了・積読に存在し、詳細未取得の本のURLだけが返る
- 読了と積読に同じ本がある場合、詳細クロール対象URLは重複しない
- 返却URLがソートされる
- 読了・積読のどちらにも存在しない `BookDetail` が削除される
- 読了または積読に紐づく `BookDetail` は削除されない
- 削除対象がない場合、既存データは変更されない
- DB確認でリストと紐づく詳細情報が表示され、空テーブルの場合は該当メッセージが表示される
- `initialize_database()` が未作成のDBファイルとテーブルを作成する
- DBファイルが既に存在する場合も、`initialize_database()` はファイルを再作成せずに `create_all()` を呼ぶ
- `session_scope()` で例外発生時にrollbackされる

### `test_bookmeter_crawl_export_search.py`
CSV出力と検索表示を検証する。

対象:

- `handle_csv_export()`
- `search_books()`

主な検証内容:

- 詳細未取得の本がある場合、CSVは出力されない
- 詳細データのASINが `None` または空文字の本はCSV出力から除外し、件数と対象書籍を警告ログに出力する
- すべての本がASIN欠落で除外される場合も、0行のCSVファイルが出力される
- DBが空の場合、0行のCSVファイルが出力される
- 詳細がすべて揃っている場合、ASINのある読了本は「読み終わった」、積読本は「積読」としてCSV出力される
- 読了日の値が `日付不明` の場合、CSVの読了日は空になる
- `search_books()` が指定キーワードをAND条件で検索する
- `target='read'`, `target='stacked'`, `target='all'` の絞り込みが効く
- 検索結果がない場合、該当なしメッセージが出力される

CSVファイルの出力先は、テスト用の一時ディレクトリに差し替える。  
`print()` の確認には pytest の `capsys` を使用する。

### `test_bookmeter_crawl_runner.py`
Scrapy起動順制御を、実際のネットワークやreactorを動かさずに検証する。

対象:

- `run_crawls()`

主な検証内容:

- `args.stacked=True` の場合、`BookmeterStackedSpider` が起動対象になる
- `args.read=True` の場合、`BookmeterReadSpider` が起動対象になる
- `args.detail=True` かつ詳細未取得URLがある場合、`BookmeterBookDetailSpider` に `target_urls` が渡される
- `stacked`, `read`, `detail` がすべて有効な場合、積読、読了、詳細の順に実行される
- 詳細未取得URLがない場合、詳細Spiderは起動されない

`runner.crawl()` はfake runnerまたはmockで置き換え、呼び出されたSpiderクラスと引数だけを記録する。

### `test_bookmeter_crawl_cli.py`
CLI引数による分岐を最小限に検証する。

対象:

- `main()`

主な検証内容:

- オプション未指定の場合、エラーになる
- `--all` 指定時に `stacked`, `read`, `detail` が有効化される
- `--deletedetail` 指定時に `handle_delete_details()` が呼ばれる
- `--csv` 指定時に `handle_csv_export()` が呼ばれる
- `--search` 指定時に `search_books()` が呼ばれる
- `--detail` のみ指定時、詳細未取得URLがない場合はScrapy reactorを起動しない
- `--detail` のみ指定時、詳細未取得URLがある場合は詳細SpiderへURLを渡してScrapy reactorを起動する

`main()` はTwisted reactorを起動する可能性があるため、厚くテストしすぎない。  
`initialize_database()`, `run_crawls()`, `handle_*()`, `search_books()`, `CrawlerRunner`, `reactor` などはmonkeypatchして、分岐だけを確認する。

### `test_bookmeter_web.py`
`cr_bookmeter/bookmeter_web.py` のWeb UI用ロジックとHTTPハンドラを検証する。

主な検証内容:

- 取得対象オプションの変換と入力チェック
- DB一覧、タイトル検索、不要詳細データの削除プレビュー、CSV出力可否の判定
- 数字・ローマ数字を含むタイトルの並び順
- CLI起動コマンドの構築、出力ログの取り込み、終了コードによる失敗判定
- ジョブの成功・失敗の記録と同時実行の拒否
- GET・POSTのルーティング、例外とHTTPステータスの対応、HTML・JSON・CSVレスポンス
- Webサーバーの起動・終了処理

CLIの子プロセス起動、スレッド、Webサーバーはfakeやmonkeypatchで置き換え、実際のクロールやサーバー起動は行わない。
DB初期化処理の隔離には、基本方針に記載した制約がある。

### `test_config.py`
`cr_bookmeter/cr_bookmeter/config.py` の `get_user_id()` を検証する。

- 環境変数 `USER_ID` が `.env` より優先される
- 環境変数が未指定の場合は `.env` を参照する
- `.env` がなくても環境変数があれば取得できる
- どちらにもユーザーIDがない場合はエラーになる

`.env` は一時ディレクトリに作成し、環境変数はmonkeypatchで制御する。

### `test_crawl_results.py`
クロール結果の収集・成功判定と、既存DBのテーブル補完を検証する。

- `evaluate_crawl_results()` が終了理由とリスト差し替え結果から成否を判定する
- 詳細Spiderではリスト差し替え結果を必要とせず、いずれかのSpiderが失敗した場合は全体も失敗となる
- `_record_crawl_result()` がstatsから終了理由、取得件数、差し替え結果を記録し、statsがない場合も処理できる
- `_run_one_crawl()` が作成したcrawlerを実行し、完了後にstatsを収集する
- 既存DBに不足しているステージングテーブルが追加され、既存テーブルは残る

クロール処理はfake runnerを使用し、テーブル補完は一時DBと差し替えた `engine`・`_db_path` で検証する。

### `test_pipeline_staging.py`
`cr_bookmeter/cr_bookmeter/pipelines.py` のステージング経由のDB反映を検証する。

- 取得したアイテムはステージングに保存され、クロール中は本テーブルを変更しない
- 正常終了時は本テーブルを取得順に差し替え、ステージングを空にする
- 異常終了時は既存データを保持する
- 取得件数が0件で本テーブルに既存データがある場合は差し替えない
- 差し替え結果と取得件数をstatsに記録する

`db_engine` fixtureで一時DBを作成し、`pipelines.engine` を差し替える。

## テスト実行方針

### 一時DBでの実行手順

現状のfixtureで本番DBへの初期化を避けるため、次のコマンドで実行する。
DBモジュールの `engine` と `_db_path` をテスト実行プロセス内で差し替えてからpytestを起動する。
`bookmeter_crawl` は差し替え後の接続先を読み込み、各テストのfixtureは引き続きテストごとの一時DBを使用する。

`USER_ID=test-user` はSpiderのインポートに必要な設定用の値であり、ネットワーク通信は発生しない。
全件実行では、事前に `test/testdata/url_map.json` と保存済みHTMLを用意しておく。

```bash
USER_ID=test-user venv/bin/python -B - <<'PY'
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine

repo = Path.cwd()
sys.path.insert(0, str(repo / "cr_bookmeter"))
from sqlite import bookmeter_db

pytest_args = ["test", "-p", "no:cacheprovider"]

with TemporaryDirectory(prefix="get-bookmeter-tests-", dir="/tmp") as temp_dir:
    temp_root = Path(temp_dir)
    bookmeter_db._db_path = temp_root / "bookmeter.db"
    bookmeter_db.engine = create_engine(f"sqlite:///{bookmeter_db._db_path}")
    try:
        exit_code = pytest.main([
            *pytest_args, "--basetemp", str(temp_root / "pytest")
        ])
    finally:
        bookmeter_db.engine.dispose()

raise SystemExit(int(exit_code))
PY
```

この手順では `slow` を含む全件を実行する。
Pythonのバイトコードとpytestのキャッシュは作成せず、一時DB・CSVなどは終了時に削除する。

保存済みHTMLのテストだけを実行する場合は、上記コードの `pytest_args` を次に置き換える。

```python
pytest_args = ["test", "-p", "no:cacheprovider", "-m", "slow"]
```

保存済みHTMLのテストを除外する場合は、次に置き換える。この場合、HTMLと `url_map.json` は不要となる。

```python
pytest_args = ["test", "-p", "no:cacheprovider", "-m", "not slow"]
```

全HTMLを対象にするテストが完了すると、読了・積読・詳細ごとのHTML件数と解析したアイテム件数を表示する。
`-m "not slow"` では全HTML解析を実行しないため、この集計は表示しない。

### fixtureのDB隔離対応後の直接実行

`Session` に加えて初期化処理の `engine` と `_db_path` も一時DBへ差し替え、本番DBに接続しないことを確認できたら、次の直接実行コマンドを使用できる。
これらのコマンドもリポジトリのルートディレクトリから実行する。

```bash
# 全件（slowを含む）
USER_ID=test-user venv/bin/pytest test

# 保存済みHTMLのテスト全体
USER_ID=test-user venv/bin/pytest test -m slow

# 保存済みHTMLのテストを除外
USER_ID=test-user venv/bin/pytest test -m "not slow"
```

### CIでの実行

GitHub Actionsの `.github/workflows/build.yml` では、`.env.example` から `.env` を用意し、`python -m pytest test -m "not slow" --cov=cr_bookmeter --cov-report=xml:coverage.xml` を実行する。
保存済みHTMLはCIに含まれないため、代表例を含む保存済みHTMLのテスト全体を除外する。

依存パッケージの準備は [README.md](../README.md#pipでインストールが必要なパッケージ) を参照する。
