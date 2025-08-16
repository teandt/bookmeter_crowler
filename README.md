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

# データ
積読本／既読本リストでは以下の情報を取得しておく
    id : 読書メーターの書籍番号
    short_title ： タイトル（長い場合は後ろが切れる）
    author ： 著者リスト。複数の著者だった場合まとめて入るのが後で課題かも？
    date ：積読本リストでは基本的にNullが入る想定。既読本リストだと読書日が入る（不明、で登録すると「日付不明」が入るので要注意）
    url ：読書メーターの書籍詳細Url
