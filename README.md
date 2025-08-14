# pipでインストールするパッケージ
- scrapy
- python-dotenv
- SQLAlchemy ※テスト用？ SQLite使うように拡張するなら使うかも

# 設定
読書メーターのユーザーIDを指定しておく必要があるので、cd_bookmeter/env/.env のUSER_ID="0000"を自分のユーザIDに変更して実行する。

# 実行方法
cd cr_bookmeter
scrapy crawl bookmeter -o output.json

# 構成のイメージ
bookmeter_crawl.pyで実行。 オプションによってどこをスクレイピングしに行くのかを指定
未読リストor既読リストを取得してSQLiteに保存、更新
書籍詳細オプションが付いている場合、各リストで詳細が取得されていない書籍の書籍ページをクロールして詳細を取得、SQLiteに保存更新
