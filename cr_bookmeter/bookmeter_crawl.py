import argparse
import logging
import csv
from contextlib import contextmanager
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

from csvdata import booklog_csv_data
from sqlalchemy.orm import sessionmaker
from twisted.internet.error import ReactorNotRestartable

logger = logging.getLogger('bookmeter_crawl')

Session = sessionmaker(bind=engine)

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def initialize_database():
    """DBファイルが存在しない場合は作成する"""
    if not _db_path.exists():
        logger.info(f"データベースファイルが見つかりません。新しいファイルを作成します: {_db_path}")
        Base.metadata.create_all(engine)
        logger.info("データベースとテーブルを作成しました。")

def get_urls_for_detail_crawl():
    """書籍詳細をクロールするためのURLリストを取得する"""
    with session_scope() as session:
        # 詳細未取得のURLをリストアップ
        read_books_no_detail = (
            session.query(ReadBooks)
            .outerjoin(BookDetail, ReadBooks.book_id == BookDetail.book_id)
            .filter(BookDetail.book_id.is_(None))
            .all()
        )
        stacked_books_no_detail = (
            session.query(StackedBooks)
            .outerjoin(BookDetail, StackedBooks.book_id == BookDetail.book_id)
            .filter(BookDetail.book_id.is_(None))
            .all()
        )
        urls = [book.url for book in read_books_no_detail]
        urls.extend([book.url for book in stacked_books_no_detail])
        return sorted(list(set(urls)))

def handle_crawling(process, args):
    """クローリング関連の処理をハンドリングする"""
    crawled_something = False
    if args.stacked:
        logger.info("積読本リストの取得をキューに追加します。")
        process.crawl(BookmeterStackedSpider)
        crawled_something = True

    if args.read:
        logger.info("読んだ本リストの取得をキューに追加します。")
        process.crawl(BookmeterReadSpider)
        crawled_something = True

    if args.detail:
        logger.info("書籍詳細の取得準備を開始します。")
        urls_to_crawl = get_urls_for_detail_crawl()
        if urls_to_crawl:
            logger.info(f"詳細未取得の書籍が {len(urls_to_crawl)} 件見つかりました。クロールをキューに追加します。")
            process.crawl(BookmeterBookDetailSpider, target_urls=urls_to_crawl)
            crawled_something = True
        else:
            logger.info("DBに存在する書籍はすべて詳細取得済みです。")
    
    return crawled_something

def handle_delete_details():
    """不要な書籍詳細データの削除処理"""
    logger.info("--- 不要な書籍詳細データの削除を開始します ---")
    with session_scope() as session:
        # BookDetail にあって ReadBooks にない、かつ StackedBooks にもない書籍詳細を探す
        details_to_delete = (
            session.query(BookDetail)
            .outerjoin(ReadBooks, BookDetail.book_id == ReadBooks.book_id)
            .outerjoin(StackedBooks, BookDetail.book_id == StackedBooks.book_id)
            .filter(ReadBooks.book_id.is_(None), StackedBooks.book_id.is_(None))
            .all()
        )

        if details_to_delete:
            logger.info(f"{len(details_to_delete)} 件の不要な書籍詳細データを削除します。")
            for detail in details_to_delete:
                logger.info(f"  - 削除対象: {detail.title} (ID: {detail.book_id})")
                session.delete(detail)
            logger.info("削除が完了しました。")
        else:
            logger.info("削除対象の不要な書籍詳細データはありませんでした。")
    logger.info("--- 不要な書籍詳細データの削除が完了しました ---")

def handle_db_checks(args):
    """DBデータ確認処理"""
    logger.info("--- DBデータ確認を開始します ---")
    with session_scope() as session:
        if args.checkstacked:
            logger.info("--- [積読本リスト] データ確認 ---")
            results = (
                session.query(StackedBooks, BookDetail)
                .outerjoin(BookDetail, StackedBooks.book_id == BookDetail.book_id)
                .order_by(StackedBooks.num)
                .all()
            )
            if results:
                logger.info(f"{len(results)} 件の積読本データが見つかりました。")
                for stacked_book, book_detail in results:
                    print(stacked_book)
                    if book_detail:
                        print(f"  └ {book_detail}")
            else:
                logger.info("積読本リストにデータはありません。")

        if args.checkread:
            logger.info("--- [読んだ本リスト] データ確認 ---")
            results = (
                session.query(ReadBooks, BookDetail)
                .outerjoin(BookDetail, ReadBooks.book_id == BookDetail.book_id)
                .order_by(ReadBooks.num)
                .all()
            )
            if results:
                logger.info(f"{len(results)} 件の読んだ本データが見つかりました。")
                for read_book, book_detail in results:
                    print(read_book)
                    if book_detail:
                        print(f"  └ {book_detail}")
            else:
                logger.info("読んだ本リストにデータはありません。")

        if args.checkdetail:
            logger.info("--- [書籍詳細] データ確認 ---")
            book_details = session.query(BookDetail).order_by(BookDetail.title).all()
            if book_details:
                logger.info(f"{len(book_details)} 件の書籍詳細データが見つかりました。")
                for book in book_details:
                    print(book)
            else:
                logger.info("書籍詳細にデータはありません。")
    logger.info("--- DBデータ確認が完了しました ---")

def handle_csv_export():
    """ブクログ形式CSV出力処理"""
    logger.info("--- ブクログ形式CSV出力処理を開始します ---")
    with session_scope() as session:
        # 事前チェック: 詳細データが揃っているか
        logger.info("書籍詳細データが全て揃っているかチェックします...")

        missing_read_count = (
            session.query(ReadBooks)
            .outerjoin(BookDetail, ReadBooks.book_id == BookDetail.book_id)
            .filter(BookDetail.book_id.is_(None))
            .count()
        )
        missing_stacked_count = (
            session.query(StackedBooks)
            .outerjoin(BookDetail, StackedBooks.book_id == BookDetail.book_id)
            .filter(BookDetail.book_id.is_(None))
            .count()
        )

        if missing_read_count > 0 or missing_stacked_count > 0:
            logger.error("書籍詳細が取得できていない本があります。CSV出力はできません。")
            if missing_read_count > 0:
                logger.error(f"読んだ本リストで {missing_read_count} 件の詳細がありません。")
            if missing_stacked_count > 0:
                logger.error(f"積読本リストで {missing_stacked_count} 件の詳細がありません。")
            logger.error("-dt オプションを指定して書籍詳細を取得してください。")
            return

        logger.info("すべての書籍詳細データが揃っています。CSVデータの作成を開始します。")
        all_books_data = []

        # 読んだ本を取得
        read_books = (
            session.query(ReadBooks, BookDetail)
            .join(BookDetail, ReadBooks.book_id == BookDetail.book_id)
            .all()
        )
        for read_book, detail in read_books:
            csv_data = booklog_csv_data(
                service_id=1,
                item_id=detail.asin,
                isbn='',
                category='',
                rating='',
                read_status="読み終わった",
                review='',
                tags='',
                private_memo='',
                registered_date='',
                read_date=read_book.date if read_book.date and read_book.date != '日付不明' else ''
            )
            all_books_data.append(csv_data)

        # 積読本を取得
        stacked_books = (
            session.query(StackedBooks, BookDetail)
            .join(BookDetail, StackedBooks.book_id == BookDetail.book_id)
            .all()
        )
        for stacked_book, detail in stacked_books:
            csv_data = booklog_csv_data(
                service_id=1,
                item_id=detail.asin,
                isbn='',
                category='',
                rating='',
                read_status="積読",
                review='',
                tags='',
                private_memo='',
                registered_date='',
                read_date=''  # 積読なので読了日なし
            )
            all_books_data.append(csv_data)

        logger.info(f"合計 {len(all_books_data)} 件のデータをCSVに出力します。")

        filename = "booklog.csv"
        logger.info(f"{filename} を作成します。")

        with open(f"./csv/{filename}", 'w', newline='', encoding='sjis', errors='replace') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            for data in all_books_data:
                writer.writerow(data.to_list())
                
        logger.info("CSVファイルの出力が完了しました。")
    logger.info("--- ブクログ形式CSV出力処理を終了します ---")

def main():
    """メイン処理"""
    # logのフォーマットはscrapyに合わせる形で指定しておく
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # コマンドライン引数の処理
    parser = argparse.ArgumentParser(
                        prog='Bookmeter Crawler',
                        description='読書メーターの未読／既読リスト取得ツール',
                        epilog='Text at the bottom of help')
    parser.add_argument('-st', '--stacked', help='積読本リスト取得', action='store_true')
    parser.add_argument('-rd', '--read', help='読んだ本リスト取得', action='store_true')
    parser.add_argument('-dt', '--detail', help='書籍詳細の取得', action='store_true')
    parser.add_argument('-ckst', '--checkstacked', help='DBのデータ確認（積読本）', action='store_true')
    parser.add_argument('-ckrd', '--checkread', help='DBのデータ確認（読んだ本）', action='store_true')
    parser.add_argument('-ckd', '--checkdetail', help='DBのデータ確認（詳細）', action='store_true')
    parser.add_argument('-deldt', '--deletedetail', help='不要な書籍詳細データを削除', action='store_true')
    parser.add_argument('-csv', '--csv', help='CSV出力', action='store_true')
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.error("少なくとも1つのオプションを指定してください。")

    initialize_database()

    crawled_something = False
    if args.stacked or args.read or args.detail:
        settings = get_project_settings()
        process = CrawlerProcess(settings, install_root_handler=False)
        crawled_something = handle_crawling(process, args)

    if crawled_something:
        try:
            logger.info("クローリング処理を開始します...")
            process.start()
            logger.info("クローリング処理が正常に完了しました。")
        except ReactorNotRestartable:
            logger.error("Reactorは再起動できません。スクリプトの構造を確認してください。")
        except Exception as e:
            logger.error(f"クローリング中に予期せぬエラーが発生しました: {e}", exc_info=True)

    if args.deletedetail:
        handle_delete_details()

    if args.checkstacked or args.checkread or args.checkdetail:
        handle_db_checks(args)

    if args.csv:
        handle_csv_export()

if __name__ == "__main__":
    main()
        