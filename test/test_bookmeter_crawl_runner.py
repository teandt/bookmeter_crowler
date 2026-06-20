from argparse import Namespace

from twisted.internet import defer

import bookmeter_crawl


class FakeRunner:
    def __init__(self):
        self.calls = []

    def crawl(self, spider_cls, **kwargs):
        self.calls.append((spider_cls, kwargs))
        return defer.succeed(None)


def args_for(**overrides):
    values = {"stacked": False, "read": False, "detail": False}
    values.update(overrides)
    return Namespace(**values)


def wait_for_completed_deferred(deferred):
    assert deferred.called
    result = deferred.result
    if isinstance(result, Exception):
        raise result
    return result


def test_run_crawls_runs_stacked_spider_when_stacked_is_enabled():
    runner = FakeRunner()

    wait_for_completed_deferred(bookmeter_crawl.run_crawls(runner, args_for(stacked=True)))

    assert runner.calls == [(bookmeter_crawl.BookmeterStackedSpider, {})]


def test_run_crawls_runs_read_spider_when_read_is_enabled():
    runner = FakeRunner()

    wait_for_completed_deferred(bookmeter_crawl.run_crawls(runner, args_for(read=True)))

    assert runner.calls == [(bookmeter_crawl.BookmeterReadSpider, {})]


def test_run_crawls_passes_missing_detail_urls_to_detail_spider(monkeypatch):
    runner = FakeRunner()
    target_urls = [
        "https://bookmeter.com/books/10",
        "https://bookmeter.com/books/20",
    ]
    monkeypatch.setattr(bookmeter_crawl, "get_urls_for_detail_crawl", lambda: target_urls)

    wait_for_completed_deferred(bookmeter_crawl.run_crawls(runner, args_for(detail=True)))

    assert runner.calls == [
        (bookmeter_crawl.BookmeterBookDetailSpider, {"target_urls": target_urls})
    ]


def test_run_crawls_runs_stacked_read_detail_in_order(monkeypatch):
    runner = FakeRunner()
    target_urls = ["https://bookmeter.com/books/30"]
    monkeypatch.setattr(bookmeter_crawl, "get_urls_for_detail_crawl", lambda: target_urls)

    wait_for_completed_deferred(
        bookmeter_crawl.run_crawls(
            runner,
            args_for(stacked=True, read=True, detail=True),
        )
    )

    assert runner.calls == [
        (bookmeter_crawl.BookmeterStackedSpider, {}),
        (bookmeter_crawl.BookmeterReadSpider, {}),
        (bookmeter_crawl.BookmeterBookDetailSpider, {"target_urls": target_urls}),
    ]


def test_run_crawls_skips_detail_spider_when_no_missing_detail_urls(monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(bookmeter_crawl, "get_urls_for_detail_crawl", lambda: [])

    wait_for_completed_deferred(bookmeter_crawl.run_crawls(runner, args_for(detail=True)))

    assert runner.calls == []
