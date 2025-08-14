# pipでインストールするパッケージ
- scrapy
- python-dotenv
- SQLAlchemy ※テスト用？ SQLite使うように拡張するなら使うかも

# 設定
読書メーターのユーザーIDを指定しておく必要があるので、cd_bookmeter/env/.env のUSER_ID="0000"を自分のユーザIDに変更して実行する。

# 実行方法
cd cr_bookmeter
scrapy crawl bookmeter -o output.json
