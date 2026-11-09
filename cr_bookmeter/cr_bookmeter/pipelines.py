# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
import logging
from itemadapter import ItemAdapter
from scrapy import signals
from sqlalchemy.orm import sessionmaker
from sqlite.bookmeter_db import (
    engine,
    StackedBooks,
    StackedBooksStaging,
    ReadBooks,
    ReadBooksStaging,
    BookDetail,
)


# リスト系スパイダーと (本テーブル, ステージングテーブル) の対応
LIST_TABLES = {
    'bookmeter_stacked': (StackedBooks, StackedBooksStaging),
    'bookmeter_read': (ReadBooks, ReadBooksStaging),
}


class CrBookmeterPipeline:
    def __init__(self):
        logging.getLogger('sqlalchemy').propagate = False

    @classmethod
    def from_crawler(cls, crawler):
        pipeline = cls()
        crawler.signals.connect(pipeline.spider_closed, signal=signals.spider_closed)
        return pipeline

    def open_spider(self, spider):
        """
        Spider開始時に呼び出される
        DBセッションの開始
        """
        Session = sessionmaker(bind=engine)
        self.session = Session()

        # リスト系スパイダーは本テーブルではなくステージングテーブルだけを初期化する。
        # 本テーブルへの反映は spider_closed でクロール成功を確認してから行うため、
        # クロールが途中で失敗しても前回取得したデータはそのまま残る。
        tables = LIST_TABLES.get(spider.name)
        if tables:
            staging_table = tables[1]
            try:
                self.session.query(staging_table).delete()
                self.session.commit()
                spider.logger.info(
                    f"--- Pipeline: Cleared all records from staging table "
                    f"'{staging_table.__tablename__}'. ---"
                )
            except Exception as e:
                spider.logger.error(
                    f"--- Pipeline: Failed to clear staging table "
                    f"'{staging_table.__tablename__}'. Error: {e} ---"
                )
                self.session.rollback()

        spider.logger.info("--- Pipeline: Database session opened. ---")

    def close_spider(self, spider):
        """
        Spider終了時に呼び出される
        DBセッションの終了
        """
        self.session.close()
        spider.logger.info("--- Pipeline: Database session closed. ---")

    def spider_closed(self, spider, reason):
        """
        Spider終了シグナルで呼び出される
        リスト系スパイダーは、クロールが正常終了した場合に限り
        ステージングテーブルの内容を本テーブルへ反映（差し替え）する。
        異常終了時や、既存データがあるのに取得件数が0件の場合は
        ステージングを破棄して本テーブルを保持する。
        結果は stats の pipeline/swap_applied 等に記録し、呼び出し側が
        終了ステータス判定に使えるようにする。
        """
        tables = LIST_TABLES.get(spider.name)
        if not tables:
            return

        main_table, staging_table = tables
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            staged_count = session.query(staging_table).count()
            main_count = session.query(main_table).count()

            # 正常終了 かつ (1件以上取得できた, または本テーブルが元々空) 場合のみ反映する。
            # 取得0件で本テーブルにデータがある場合は、サイト側の異常や
            # 取得失敗の可能性が高いため反映しない（データ全損の防止）。
            swap_ok = (reason == 'finished') and (staged_count > 0 or main_count == 0)

            stats = getattr(getattr(spider, 'crawler', None), 'stats', None)
            if stats is not None:
                stats.set_value('pipeline/staged_items', staged_count)
                stats.set_value('pipeline/swap_applied', swap_ok)

            if swap_ok:
                staged_rows = (
                    session.query(staging_table)
                    .order_by(staging_table.num)
                    .all()
                )
                session.query(main_table).delete()
                for row in staged_rows:
                    session.add(main_table(
                        book_id=row.book_id,
                        title=row.title,
                        authors=row.authors,
                        date=row.date,
                        url=row.url,
                    ))
                session.query(staging_table).delete()
                session.commit()
                spider.logger.info(
                    f"--- Pipeline: Applied staging to '{main_table.__tablename__}' "
                    f"({staged_count} items, previous {main_count} items). ---"
                )
            else:
                session.query(staging_table).delete()
                session.commit()
                spider.logger.warning(
                    f"--- Pipeline: Crawl did not complete successfully "
                    f"(reason={reason}, staged={staged_count}, current={main_count}). "
                    f"Kept existing data in '{main_table.__tablename__}'. ---"
                )
        except Exception as e:
            session.rollback()
            spider.logger.error(f"--- Pipeline: Failed to apply staging. Error: {e} ---")
            raise
        finally:
            session.close()

    def process_item(self, item, spider):
        # spider.nameでどのスパイダーから渡されたItemかを判別
        if spider.name in LIST_TABLES:
            staging_table = LIST_TABLES[spider.name][1]
            adapter = ItemAdapter(item)
            staged_book = staging_table(
                book_id=adapter.get('id'),
                title=adapter.get('short_title'),
                authors=adapter.get('authors'),
                date=adapter.get('date'),
                url=adapter.get('url'),
            )
            try:
                self.session.add(staged_book)
                self.session.commit()
                spider.logger.debug(f"Saved staged book: {adapter.get('short_title')}")
            except Exception as e:
                spider.logger.error(f"Failed to save staged book to DB: {e}")
                self.session.rollback()
                raise
            return item

        elif spider.name == 'bookmeter_bookdetail':
            adapter = ItemAdapter(item)
            book_detail = BookDetail(
                book_id = adapter.get('id'),
                title = adapter.get('title'),
                pages = adapter.get('pages'),
                amazon_url = adapter.get('amazon_url'),
                asin = adapter.get('asin')
            )
            try:
                # session.merge() を使うと、主キーが同じデータがあれば更新、なければ挿入（UPSERT）してくれます
                self.session.merge(book_detail)
                self.session.commit()
                spider.logger.debug(f"Saved book detail to DB: {adapter.get('title')}")
            except Exception as e:
                spider.logger.error(f"Failed to save book detail to DB: {e}")
                self.session.rollback()
                raise
            return item

        # 上記以外のスパイダーの場合は、そのままItemを返します
        return item
