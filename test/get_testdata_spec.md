# 実行環境
pythonのライブラリ等の実行環境はvenvで作成した仮想環境で実行してください。  
必要なライブラリがある場合、この仮想環境の中でインストールする必要があります。  

# テストデータ取得方針
テストコードを作成するためまずはテストデータを取得する。  
普段使っているWebページから現在のページを取得して保存、テストに使用することとする。

## テストデータ取得

`test/get_testdata.py` を実行して、`.env`（`cr_bookmeter/env/.env`）に記載されている `USER_ID` のページをクロールし、テスト用の HTML データを取得します。

### 出力ディレクトリ構成
取得したデータは `./test/testdata/` 以下に分類して保存されます。
- `test/testdata/page/read/read_*.html` （読んだ本リスト）
- `test/testdata/page/stacked/stacked_*.html` （積読本リスト）
- `test/testdata/page/detail/detail_*.html` （書籍詳細）
- `test/testdata/url_map.json` （URLとローカルHTMLファイルの対応マップ）

### ツールオプション (`get_testdata.py`)
- `--force`: キャッシュを無視して強制的にダウンロードし直します。
- `--delay`: リクエスト間の待機秒数（デフォルト: 3.0秒）。
- `--limit-pages`: リスト取得の最大ページ数（デフォルト: 0（無制限））。テスト用に一部だけ取得したい場合は `1` や `2` などを指定します。
- `--limit-books`: 取得する書籍詳細ページの最大数（デフォルト: 0（無制限））。

### 特徴
- **再開（レジューム）機能**: すでにローカルに対応するHTMLファイルが存在する場合、ネットワークアクセスをスキップします。一時エラー等で処理が中断された場合、再度実行すれば未取得のファイルから自動で再開されます。
- **堅牢なエラーハンドリング**: 503エラーなどが発生してもスクリプトを終了させず、その書籍詳細のみをスキップして次の処理へ進み、最後まで取得を継続します（未取得分は次回の実行時に再開可能）。

## テストコードでの利用イメージ

HTML ファイル内のリンク（`href`）をローカルパスに置換してしまうと、本番用の抽出ロジック（URLやASINの抽出等）を正確にテストできなくなるため、HTML は置換せず本番そのままの構造で保存しています。

テスト時には `url_map.json` を利用して、テストコード側でリクエストをモックします。

### Pythonによるモックテスト例

```python
import json
from scrapy.http import HtmlResponse, Request
from cr_bookmeter.spiders.bookmeter_read import BookmeterReadSpider

def test_bookmeter_read_spider():
    spider = BookmeterReadSpider()
    
    # 1. url_map.json から URL とローカルファイルの対応マップを読み込む
    with open("test/testdata/url_map.json", "r", encoding="utf-8") as f:
        url_map = json.load(f)
        
    # 2. ローカルファイルのパスからテスト対象URLを逆引き
    target_path = "page/read/read_1.html"
    target_urls = [
        url for url, local_path in url_map.items()
        if local_path == target_path
    ]
    assert len(target_urls) == 1
    target_url = target_urls[0]
    local_path = f"test/testdata/{target_path}"
    
    with open(local_path, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    # 3. Scrapy Response をモック
    response = HtmlResponse(
        url=target_url,
        body=html_content.encode("utf-8"),
        encoding="utf-8",
        request=Request(url=target_url)
    )
    
    # 4. spider のパース処理を実行し、結果を検証
    results = list(spider.parse(response))
    assert len(results) > 0
    assert results[0]["id"] is not None
```