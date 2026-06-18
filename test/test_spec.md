# テストコード生成方針
テストデータを./test/testdataに取得しているので、このデータを使って./cr_bookmeter/bookmeter_crawl.pyのテストを実行するテストコードを作成する。  
テストデータの取得方法については./test/get_testdata_spec.mdにもとづいてスクリプトを作成して取得している。  

# テストコード実行環境
bookmeter_crawl.pyと同様にvenvの仮想環境化で実行すること。  

# テストコード構成

## 基本方針
`cr_bookmeter/bookmeter_crawl.py` は、HTML解析そのものではなく、DB操作、CSV出力、Scrapy起動順制御、CLI分岐を担当するオーケストレーション層である。  
そのため、保存済みHTMLを使うSpider解析テストと、`bookmeter_crawl.py` のDB・制御ロジックのテストを分けて作成する。

実ネットワークへのアクセスは行わない。  
`test/testdata/url_map.json` と `test/testdata/page/**/*.html` を利用し、Scrapyの `HtmlResponse` をテストコード側で生成してSpiderの `parse()` を直接検証する。

本番DB `cr_bookmeter/sqlite/bookmeter.db` はテストで直接使用しない。  
pytest fixtureで一時SQLite DBを作成し、`bookmeter_crawl.Session` をmonkeypatchして、テストDBだけを操作する。

## 推奨ファイル構成

```text
test/
  conftest.py
  test_spiders_from_testdata.py
  test_bookmeter_crawl_db.py
  test_bookmeter_crawl_export_search.py
  test_bookmeter_crawl_runner.py
  test_bookmeter_crawl_cli.py
```

## 各テストファイルの役割

### `conftest.py`
テスト共通のfixtureを定義する。

- 一時SQLite DBを作成するfixture
- `bookmeter_crawl.Session` をテスト用DBへ差し替えるfixture
- `test/testdata/url_map.json` を読み込むfixture
- ローカルHTMLから `HtmlResponse` を生成するヘルパーfixture
- 必要に応じて `sys.path` やカレントディレクトリを調整するfixture

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

通常テストでは代表的なHTMLを数件だけ使う。  
全HTMLを対象にする網羅テストは実行時間が長くなるため、`pytest -m slow` などで任意実行できるテストとして分ける。

### `test_bookmeter_crawl_db.py`
`bookmeter_crawl.py` のDB操作ロジックを一時DBで検証する。

対象:

- `get_urls_for_detail_crawl()`
- `handle_delete_details()`
- `initialize_database()`
- `session_scope()`

主な検証内容:

- 読了・積読に存在し、詳細未取得の本のURLだけが返る
- 読了と積読に同じ本がある場合、詳細クロール対象URLは重複しない
- 返却URLがソートされる
- 読了・積読のどちらにも存在しない `BookDetail` が削除される
- 読了または積読に紐づく `BookDetail` は削除されない
- 削除対象がない場合、既存データは変更されない
- DBファイルが既に存在する場合、`initialize_database()` は再作成しない
- `session_scope()` で例外発生時にrollbackされる

### `test_bookmeter_crawl_export_search.py`
CSV出力と検索表示を検証する。

対象:

- `handle_csv_export()`
- `search_books()`

主な検証内容:

- 詳細未取得の本がある場合、CSVは出力されない
- 詳細データのASINが `None` または空文字の場合、CSVは出力されない
- DBが空の場合、0行のCSVファイルが出力される
- 詳細がすべて揃っている場合、読了本は「読み終わった」、積読本は「積読」としてCSV出力される
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

## 優先順位

まず以下の順で作成する。

1. `test_spiders_from_testdata.py`
2. `test_bookmeter_crawl_db.py`
3. `test_bookmeter_crawl_export_search.py`
4. `test_bookmeter_crawl_runner.py`
5. `test_bookmeter_crawl_cli.py`

最初にSpider解析とDBロジックを固める。  
この2つが、読書メーターのHTML変更検知と、アプリの主要データ処理の保護に直結するためである。

## テスト実行方針

通常実行:

```bash
venv/bin/pytest test
```

`pytest.ini` の設定により、通常実行では `slow` マーカー付きテストを除外する。

全HTMLを使う重いテストのみを実行する場合:

```bash
venv/bin/pytest test -m slow
```

完了時には、読了・積読・詳細ごとに確認したHTML件数と解析したアイテム件数を表示する。

テストコードはvenv上で実行する。  
必要なライブラリが不足している場合は、venv内にインストールする。
