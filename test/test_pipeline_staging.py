"""ステージング経由のDB反映（pipelines）のテスト。

リスト系スパイダーは本テーブルを直接書き換えず、ステージングテーブルに
集めてから、クロール成功時にだけ本テーブルへ差し替えることを確認する。
"""
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cr_bookmeter import pipelines
from cr_bookmeter.items import CrBookmeterItem
from sqlite.bookmeter_db import (
    Base,
    ReadBooks,
    ReadBooksStaging,
    StackedBooks,
    StackedBooksStaging,
)


class FakeStats:
    def __init__(self):
        self.values = {}

    def set_value(self, key, value):
        self.values[key] = value


class FakeCrawler:
    def __init__(self):
        self.stats = FakeStats()


class FakeSpider:
    def __init__(self, name):
        self.name = name
        self.logger = logging.getLogger("test_pipeline_staging")
        self.crawler = FakeCrawler()


@pytest.fixture
def db_engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline_test.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(pipelines, "engine", engine)
    return engine


def make_session(engine):
    return sessionmaker(bind=engine)()


def seed_main(engine, rows):
    session = make_session(engine)
    for model, values in rows:
        session.add(model(**values))
    session.commit()
    session.close()


def main_titles(engine, model):
    session = make_session(engine)
    titles = [row.title for row in session.query(model).order_by(model.num).all()]
    session.close()
    return titles


def count_rows(engine, model):
    session = make_session(engine)
    count = session.query(model).count()
    session.close()
    return count


def make_item(book_id, title):
    item = CrBookmeterItem()
    item["id"] = book_id
    item["short_title"] = title
    item["authors"] = "著者"
    item["date"] = "2026/01/01"
    item["url"] = f"https://bookmeter.com/books/{book_id}"
    return item


def test_items_go_to_staging_not_main(db_engine):
    seed_main(db_engine, [
        (ReadBooks, dict(book_id="1", title="旧タイトル", authors="a",
                         date="2025/01/01", url="https://bookmeter.com/books/1")),
    ])
    spider = FakeSpider("bookmeter_read")
    pipeline = pipelines.CrBookmeterPipeline()
    pipeline.open_spider(spider)
    pipeline.process_item(make_item("2", "新タイトル"), spider)
    pipeline.close_spider(spider)

    # クロール中は本テーブルに触れない
    assert main_titles(db_engine, ReadBooks) == ["旧タイトル"]
    assert count_rows(db_engine, ReadBooksStaging) == 1


def test_swap_applied_on_finished(db_engine):
    seed_main(db_engine, [
        (ReadBooks, dict(book_id="1", title="旧1", authors="a",
                         date="2025/01/01", url="https://bookmeter.com/books/1")),
        (ReadBooks, dict(book_id="2", title="旧2", authors="a",
                         date="2025/01/02", url="https://bookmeter.com/books/2")),
    ])
    spider = FakeSpider("bookmeter_read")
    pipeline = pipelines.CrBookmeterPipeline()
    pipeline.open_spider(spider)
    pipeline.process_item(make_item("3", "新1"), spider)
    pipeline.process_item(make_item("4", "新2"), spider)
    pipeline.process_item(make_item("5", "新3"), spider)
    pipeline.close_spider(spider)
    pipeline.spider_closed(spider, "finished")

    # 本テーブルが新しい内容に差し替わり、順序も保持される
    assert main_titles(db_engine, ReadBooks) == ["新1", "新2", "新3"]
    assert count_rows(db_engine, ReadBooksStaging) == 0
    assert spider.crawler.stats.values["pipeline/swap_applied"] is True
    assert spider.crawler.stats.values["pipeline/staged_items"] == 3


def test_swap_not_applied_on_abnormal_close(db_engine):
    seed_main(db_engine, [
        (StackedBooks, dict(book_id="1", title="既存の積読", authors="a",
                            date=None, url="https://bookmeter.com/books/1")),
    ])
    spider = FakeSpider("bookmeter_stacked")
    pipeline = pipelines.CrBookmeterPipeline()
    pipeline.open_spider(spider)
    pipeline.process_item(make_item("2", "途中まで取得した本"), spider)
    pipeline.close_spider(spider)
    pipeline.spider_closed(spider, "shutdown")

    # 異常終了時は本テーブルを保持し、ステージングは破棄する
    assert main_titles(db_engine, StackedBooks) == ["既存の積読"]
    assert count_rows(db_engine, StackedBooksStaging) == 0
    assert spider.crawler.stats.values["pipeline/swap_applied"] is False


def test_swap_not_applied_when_zero_items_and_main_not_empty(db_engine):
    seed_main(db_engine, [
        (ReadBooks, dict(book_id="1", title="既存データ", authors="a",
                         date="2025/01/01", url="https://bookmeter.com/books/1")),
    ])
    spider = FakeSpider("bookmeter_read")
    pipeline = pipelines.CrBookmeterPipeline()
    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    pipeline.spider_closed(spider, "finished")

    # 正常終了でも取得0件なら、サイト側異常とみなして既存データを守る
    assert main_titles(db_engine, ReadBooks) == ["既存データ"]
    assert spider.crawler.stats.values["pipeline/swap_applied"] is False


def test_swap_applied_when_zero_items_and_main_empty(db_engine):
    spider = FakeSpider("bookmeter_read")
    pipeline = pipelines.CrBookmeterPipeline()
    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    pipeline.spider_closed(spider, "finished")

    # 本テーブルが空なら0件でも正常（対象リストが本当に空のケース）
    assert count_rows(db_engine, ReadBooks) == 0
    assert spider.crawler.stats.values["pipeline/swap_applied"] is True
