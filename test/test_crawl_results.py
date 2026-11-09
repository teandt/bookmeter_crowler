"""クロール結果の集計と終了ステータス判定（bookmeter_crawl）のテスト。"""
from twisted.internet import defer

import bookmeter_crawl


def result(**overrides):
    base = {
        "spider": "bookmeter_read",
        "finish_reason": "finished",
        "items": 10,
        "swap_applied": True,
    }
    base.update(overrides)
    return base


def test_evaluate_ok_when_finished_and_swapped():
    ok, lines = bookmeter_crawl.evaluate_crawl_results([result()])
    assert ok is True
    assert "result=OK" in lines[0]
    assert "swap=applied" in lines[0]


def test_evaluate_failed_when_swap_kept():
    ok, lines = bookmeter_crawl.evaluate_crawl_results([result(swap_applied=False)])
    assert ok is False
    assert "result=FAILED" in lines[0]
    assert "swap=kept" in lines[0]


def test_evaluate_failed_when_abnormal_finish():
    ok, _ = bookmeter_crawl.evaluate_crawl_results(
        [result(finish_reason="shutdown", swap_applied=False)]
    )
    assert ok is False


def test_evaluate_failed_when_finish_reason_unknown():
    ok, _ = bookmeter_crawl.evaluate_crawl_results(
        [result(finish_reason=None, swap_applied=None)]
    )
    assert ok is False


def test_evaluate_ok_for_detail_spider_without_swap():
    ok, lines = bookmeter_crawl.evaluate_crawl_results([
        result(spider="bookmeter_bookdetail", swap_applied=None, items=5)
    ])
    assert ok is True
    assert "swap=-" in lines[0]


def test_evaluate_failed_when_any_spider_failed():
    ok, lines = bookmeter_crawl.evaluate_crawl_results([
        result(),
        result(spider="bookmeter_stacked", finish_reason="shutdown",
               swap_applied=False),
    ])
    assert ok is False
    assert len(lines) == 2


class FakeStatsCollector:
    def __init__(self, stats):
        self._stats = stats

    def get_stats(self):
        return self._stats


def test_record_crawl_result_reads_stats():
    bookmeter_crawl.CRAWL_RESULTS.clear()

    recorded = bookmeter_crawl._record_crawl_result("bookmeter_read", {
        "finish_reason": "finished",
        "item_scraped_count": 42,
        "pipeline/swap_applied": True,
    })

    assert recorded == {
        "spider": "bookmeter_read",
        "finish_reason": "finished",
        "items": 42,
        "swap_applied": True,
    }
    assert bookmeter_crawl.CRAWL_RESULTS == [recorded]


def test_record_crawl_result_tolerates_missing_stats():
    bookmeter_crawl.CRAWL_RESULTS.clear()

    recorded = bookmeter_crawl._record_crawl_result("bookmeter_read", None)

    assert recorded["spider"] == "bookmeter_read"
    assert recorded["finish_reason"] is None


class FakeCrawlerObj:
    def __init__(self, stats):
        self.stats = FakeStatsCollector(stats)


class FakeRunnerWithCreateCrawler:
    """create_crawler を持つ runner（実物の CrawlerRunner 相当）。"""

    def __init__(self, stats):
        self._stats = stats
        self.created_with = []
        self.crawl_calls = []

    def create_crawler(self, spider_cls):
        self.created_with.append(spider_cls)
        self.crawler = FakeCrawlerObj(self._stats)
        return self.crawler

    def crawl(self, crawler, **kwargs):
        self.crawl_calls.append((crawler, kwargs))
        return defer.succeed(None)


def wait_for_completed_deferred(deferred):
    assert deferred.called
    if isinstance(deferred.result, Exception):
        raise deferred.result


def test_run_one_crawl_records_stats_from_created_crawler():
    bookmeter_crawl.CRAWL_RESULTS.clear()
    runner = FakeRunnerWithCreateCrawler({
        "finish_reason": "finished",
        "item_scraped_count": 7,
        "pipeline/swap_applied": True,
    })

    wait_for_completed_deferred(
        bookmeter_crawl._run_one_crawl(runner, bookmeter_crawl.BookmeterReadSpider)
    )

    # crawler を作ってから crawl に渡している（完了後に stats を読むため）
    assert runner.created_with == [bookmeter_crawl.BookmeterReadSpider]
    assert runner.crawl_calls == [(runner.crawler, {})]
    assert bookmeter_crawl.CRAWL_RESULTS == [{
        "spider": "bookmeter_read",
        "finish_reason": "finished",
        "items": 7,
        "swap_applied": True,
    }]


def test_initialize_database_adds_missing_tables_to_existing_db(tmp_path, monkeypatch):
    """既存DBファイルがある場合でも、不足テーブル（ステージング等）が追加される。"""
    from sqlalchemy import create_engine, inspect

    db_path = tmp_path / "existing.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # 旧バージョン相当: 本テーブルだけがある状態を作る
    bookmeter_crawl.ReadBooks.__table__.create(engine)
    assert db_path.exists()

    monkeypatch.setattr(bookmeter_crawl, "engine", engine)
    monkeypatch.setattr(bookmeter_crawl, "_db_path", db_path)
    bookmeter_crawl.initialize_database()

    table_names = set(inspect(engine).get_table_names())
    assert "read_books_staging" in table_names
    assert "stacked_books_staging" in table_names
    # 既存テーブルはそのまま残る
    assert "read_books" in table_names
