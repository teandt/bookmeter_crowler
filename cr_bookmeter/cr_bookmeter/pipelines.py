# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
from sqlalchemy.orm import sessionmaker
from sqlite.bookmeter_db import engine, StackedBooks, ReadBooks, BookDetail


class CrBookmeterPipeline:
    def open_spider(self, spider):
        """
        Spider開始時に呼び出される
        DBセッションの開始
        """
        Session = sessionmaker(bind=engine)
        self.session = Session()

        # スパイダーに応じてテーブルを初期化（全件削除）する
        target_table = None
        if spider.name == 'bookmeter_stacked':
            target_table = StackedBooks
        elif spider.name == 'bookmeter_read':
            target_table = ReadBooks

        if target_table:
            try:
                table_name = target_table.__tablename__
                self.session.query(target_table).delete()
                self.session.commit()
                spider.logger.info(f"--- Pipeline: Cleared all records from '{table_name}' table. ---")
            except Exception as e:
                table_name = target_table.__tablename__
                spider.logger.error(f"--- Pipeline: Failed to clear table '{table_name}'. Error: {e} ---")
                self.session.rollback()

        spider.logger.info("--- Pipeline: Database session opened. ---")

    def close_spider(self, spider):
        """
        Spider終了時に呼び出される
        DBセッションの終了
        """
        self.session.close()
        spider.logger.info("--- Pipeline: Database session closed. ---")

    def process_item(self, item, spider):
        # spider.nameでどのスパイダーから渡されたItemかを判別
        if spider.name == 'bookmeter_read':
            adapter = ItemAdapter(item)
            read_book = ReadBooks(
                book_id=adapter.get('id'),
                title=adapter.get('short_title'),
                authors=adapter.get('authors'),
                date=adapter.get('date'),
                url=adapter.get('url')
            )
            try:
                # テーブルは起動時にクリアしているので、単純にaddする
                self.session.add(read_book)
                self.session.commit()
                spider.logger.debug(f"Saved read book to DB: {adapter.get('short_title')}")
            except Exception as e:
                spider.logger.error(f"Failed to save read book to DB: {e}")
                self.session.rollback()
                raise
            return item
        
        elif spider.name == 'bookmeter_stacked':
            adapter = ItemAdapter(item)
            # StackedBooksモデルのインスタンスを作成
            stacked_book = StackedBooks(
                book_id = adapter.get('id'),
                title = adapter.get('short_title'),
                authors = adapter.get('authors'),
                date = adapter.get('date'),
                url = adapter.get('url')
            )
            try:
                # テーブルは起動時にクリアしているので、単純にaddする
                self.session.add(stacked_book)
                self.session.commit()
                spider.logger.debug(f"Saved stacked book to DB: {adapter.get('short_title')}")
            except Exception as e:
                spider.logger.error(f"Failed to save stacked book to DB: {e}")
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
