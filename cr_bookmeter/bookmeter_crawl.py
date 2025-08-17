import argparse
import logging
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from cr_bookmeter.spiders.bookmeter_read import BookmeterReadSpider
from cr_bookmeter.spiders.bookmeter_stacked import BookmeterStackedSpider
from cr_bookmeter.spiders.bookmeter_bookdetail import BookmeterBookDetailSpider
from sqlite.bookmeter_db import (
    Base,
    BookDetail,
    ReadBooks,
    StackedBooks,
    _db_path,
    engine,
)
from sqlalchemy.orm import sessionmaker
from twisted.internet.error import ReactorNotRestartable

# logのフォーマットはscrapyに合わせる形で指定しておく
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger('bookmeter_crawl')

# コマンドライン引数の処理
parser = argparse.ArgumentParser(
                    prog='Bookmeter Crawler',
                    description='読書メーターの未読／既読リスト取得ツール',
                    epilog='Text at the bottom of help')
parser.add_argument('-st', '--stacked', help='積読本リスト取得', action='store_true')
parser.add_argument('-rd', '--read', help='読んだ本リスト取得', action='store_true')
parser.add_argument('-vb', '--verbose', help='書籍詳細の取得', action='store_true')
parser.add_argument('-ckst', '--checkstacked', help='DBのデータ確認（積読本）', action='store_true')
parser.add_argument('-ckrd', '--checkread', help='DBのデータ確認（読んだ本）', action='store_true')
parser.add_argument('-ckd', '--checkdetail', help='DBのデータ確認（詳細）', action='store_true')
args = parser.parse_args()

if not any(vars(args).values()):
    parser.error("少なくとも1つのオプション (-st, -rd, -vb) を指定してください。")

if __name__ == "__main__":

    # DBファイルが存在しない場合は作成する
    if not _db_path.exists():
        logger.info(f"データベースファイルが見つかりません。新しいファイルを作成します: {_db_path}")
        # sqlite/bookmeter_db.pyで定義されたテーブルをすべて作成
        Base.metadata.create_all(engine)
        logger.info("データベースとテーブルを作成しました。")

    # CrawlerProcessは一度だけ初期化し、実行したいスパイダーをすべて追加してから
    # 最後に一度だけstart()を呼び出します。
    settings = get_project_settings()
    process = CrawlerProcess(settings, install_root_handler=False)

    crawled_something = False
    # 積読本リストの取得を行う場合
    if args.stacked:
        logger.info("積読本リストの取得をキューに追加します。")
        process.crawl(BookmeterStackedSpider)
        crawled_something = True

    # 読んだ本リストの取得を行う場合
    if args.read:
        logger.info("読んだ本リストの取得をキューに追加します。")
        process.crawl(BookmeterReadSpider)
        crawled_something = True

    # 書籍詳細の取得が指定されている場合、DBから未取得のURLリストを取得
    urls_to_crawl_for_detail = []
    if args.verbose:
        logger.info("書籍詳細の取得準備を開始します。")
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            # 詳細未取得のURLをリストアップ
            # outerjoinを使い、BookDetailにエントリがないものを抽出
            books_no_detail = (
                session.query(ReadBooks)
                .outerjoin(BookDetail, ReadBooks.book_id == BookDetail.book_id)
                .filter(BookDetail.book_id.is_(None))
                .all()
            )
            urls_to_crawl_for_detail.extend([book.url for book in books_no_detail])

            books_no_detail = (
                session.query(StackedBooks)
                .outerjoin(BookDetail, StackedBooks.book_id == BookDetail.book_id)
                .filter(BookDetail.book_id.is_(None))
                .all()
            )
            urls_to_crawl_for_detail.extend([book.url for book in books_no_detail])

            # 重複を削除
            urls_to_crawl_for_detail = sorted(list(set(urls_to_crawl_for_detail)))

        finally:
            session.close()

    # 詳細取得用のスパイダーをキューに追加
    if args.verbose and urls_to_crawl_for_detail:
        logger.info(f"詳細未取得の書籍が {len(urls_to_crawl_for_detail)} 件見つかりました。クロールをキューに追加します。")
        process.crawl(BookmeterBookDetailSpider, target_urls=urls_to_crawl_for_detail)
        crawled_something = True
    elif args.verbose:
        logger.info("DBに存在する書籍はすべて詳細取得済みです。")

    # キューにスパイダーが追加されている場合のみ、クローリングを開始します。
    if crawled_something:
        try:
            logger.info("クローリング処理を開始します...")
            process.start()
            logger.info("クローリング処理が正常に完了しました。")
        except ReactorNotRestartable:
            logger.error("Reactorは再起動できません。スクリプトの構造を確認してください。")
        except Exception as e:
            logger.error(f"クローリング中に予期せぬエラーが発生しました: {e}", exc_info=True)

    if args.checkstacked:
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            logger.info("--- [積読本リスト] データ確認 ---")
            # タイトル順でソートして取得
            stacked_books = session.query(StackedBooks).order_by(StackedBooks.num).all()
            if stacked_books:
                logger.info(f"{len(stacked_books)} 件の積読本データが見つかりました。")
                for book in stacked_books:
                    # DBモデルの__repr__メソッドで定義した形式で出力されます
                    print(book)
            else:
                logger.info("積読本リストにデータはありません。")
        finally:
            session.close()
            logger.info("--- DBセッションをクローズしました ---")

    if args.checkread:
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            logger.info("--- [読んだ本リスト] データ確認 ---")
            # タイトル順でソートして取得
            read_books = session.query(ReadBooks).order_by(ReadBooks.num).all()
            if read_books:
                logger.info(f"{len(read_books)} 件の積読本データが見つかりました。")
                for book in read_books:
                    # DBモデルの__repr__メソッドで定義した形式で出力されます
                    print(book)
            else:
                logger.info("積読本リストにデータはありません。")
        finally:
            session.close()
            logger.info("--- DBセッションをクローズしました ---") 

    if args.checkdetail:
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            logger.info("--- [書籍詳細] データ確認 ---")
            # タイトル順でソートして取得
            book_details = session.query(BookDetail).order_by(BookDetail.title).all()
            if book_details:
                logger.info(f"{len(book_details)} 件の書籍詳細データが見つかりました。")
                for book in book_details:
                    # DBモデルの__repr__メソッドで定義した形式で出力されます
                    print(book)
            else:
                logger.info("書籍詳細にデータはありません。")
        finally:
            session.close()
            logger.info("--- DBセッションをクローズしました ---")
        