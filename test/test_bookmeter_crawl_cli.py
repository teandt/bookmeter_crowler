import sys

import pytest
from twisted.internet import defer

import bookmeter_crawl


class FakeDeferred:
    def __init__(self):
        self.added_callback = False

    def addBoth(self, callback):
        self.added_callback = True
        callback(None)
        return self


class FakeSettings:
    def get(self, name):
        assert name == "TWISTED_REACTOR"
        return None


def set_argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["bookmeter_crawl.py", *args])


def patch_reactor_startup(monkeypatch, calls):
    import scrapy.utils.reactor as scrapy_reactor
    from twisted.internet import reactor

    class FakeCrawlerRunner:
        def __init__(self, settings):
            self.settings = settings
            calls.append(("CrawlerRunner", settings))

        def crawl(self, spider_cls, **kwargs):
            calls.append(("crawl", spider_cls, kwargs))
            return defer.succeed(None)

    monkeypatch.setattr(bookmeter_crawl, "get_project_settings", lambda: FakeSettings())
    monkeypatch.setattr(bookmeter_crawl, "CrawlerRunner", FakeCrawlerRunner)
    monkeypatch.setattr(scrapy_reactor, "install_reactor", lambda reactor_path: calls.append(("install_reactor", reactor_path)))
    monkeypatch.setattr(reactor, "stop", lambda: calls.append(("reactor.stop",)))
    monkeypatch.setattr(reactor, "run", lambda: calls.append(("reactor.run",)))


def test_main_errors_when_no_option_is_given(monkeypatch, capsys):
    set_argv(monkeypatch)

    with pytest.raises(SystemExit) as excinfo:
        bookmeter_crawl.main()

    assert excinfo.value.code == 2
    assert "少なくとも1つのオプションを指定してください。" in capsys.readouterr().err


def test_main_all_enables_stacked_read_detail_and_runs_crawler(monkeypatch):
    calls = []
    captured = {}
    set_argv(monkeypatch, "--all")
    patch_reactor_startup(monkeypatch, calls)
    monkeypatch.setattr(bookmeter_crawl, "initialize_database", lambda: calls.append(("initialize_database",)))

    def fake_run_crawls(runner, args):
        captured["args"] = args
        captured["runner"] = runner
        calls.append(("run_crawls", args.stacked, args.read, args.detail))
        return FakeDeferred()

    monkeypatch.setattr(bookmeter_crawl, "run_crawls", fake_run_crawls)

    bookmeter_crawl.main()

    assert captured["args"].stacked is True
    assert captured["args"].read is True
    assert captured["args"].detail is True
    assert calls == [
        ("initialize_database",),
        ("install_reactor", None),
        ("CrawlerRunner", captured["runner"].__dict__.get("settings")),
        ("run_crawls", True, True, True),
        ("reactor.stop",),
        ("reactor.run",),
    ]


def test_main_detail_only_does_not_run_crawler_when_no_missing_detail_urls(monkeypatch):
    calls = []
    set_argv(monkeypatch, "--detail")
    monkeypatch.setattr(bookmeter_crawl, "initialize_database", lambda: calls.append(("initialize_database",)))
    monkeypatch.setattr(bookmeter_crawl, "get_urls_for_detail_crawl", lambda: calls.append(("get_urls_for_detail_crawl",)) or [])
    monkeypatch.setattr(bookmeter_crawl, "CrawlerRunner", lambda settings: pytest.fail("CrawlerRunner should not be created"))
    monkeypatch.setattr(bookmeter_crawl, "run_crawls", lambda runner, args: pytest.fail("run_crawls should not be called"))

    bookmeter_crawl.main()

    assert calls == [("initialize_database",), ("get_urls_for_detail_crawl",)]


def test_main_detail_only_runs_detail_spider_when_missing_urls_exist(monkeypatch):
    calls = []
    target_urls = ["https://bookmeter.com/books/10"]
    set_argv(monkeypatch, "--detail")
    patch_reactor_startup(monkeypatch, calls)
    monkeypatch.setattr(
        bookmeter_crawl,
        "initialize_database",
        lambda: calls.append(("initialize_database",)),
    )

    def fake_get_urls_for_detail_crawl():
        calls.append(("get_urls_for_detail_crawl",))
        return target_urls

    monkeypatch.setattr(
        bookmeter_crawl,
        "get_urls_for_detail_crawl",
        fake_get_urls_for_detail_crawl,
    )

    bookmeter_crawl.main()

    assert [call[0] for call in calls] == [
        "initialize_database",
        "get_urls_for_detail_crawl",
        "install_reactor",
        "CrawlerRunner",
        "get_urls_for_detail_crawl",
        "crawl",
        "reactor.stop",
        "reactor.run",
    ]
    assert (
        "crawl",
        bookmeter_crawl.BookmeterBookDetailSpider,
        {"target_urls": target_urls},
    ) in calls


def test_main_check_options_call_handle_db_checks(monkeypatch):
    captured = {}
    set_argv(monkeypatch, "--checkread")
    monkeypatch.setattr(bookmeter_crawl, "initialize_database", lambda: None)
    monkeypatch.setattr(bookmeter_crawl, "handle_db_checks", lambda args: captured.setdefault("args", args))

    bookmeter_crawl.main()

    assert captured["args"].checkread is True
    assert captured["args"].checkstacked is False
    assert captured["args"].checkdetail is False


def test_main_dispatches_delete_csv_and_search_handlers(monkeypatch):
    calls = []
    set_argv(monkeypatch, "--deletedetail", "--csv", "--search", "Python", "Testing", "--target", "stacked")
    monkeypatch.setattr(bookmeter_crawl, "initialize_database", lambda: calls.append(("initialize_database",)))
    monkeypatch.setattr(bookmeter_crawl, "handle_delete_details", lambda: calls.append(("handle_delete_details",)))
    monkeypatch.setattr(bookmeter_crawl, "handle_csv_export", lambda: calls.append(("handle_csv_export",)))
    monkeypatch.setattr(bookmeter_crawl, "search_books", lambda keywords, target: calls.append(("search_books", keywords, target)))

    bookmeter_crawl.main()

    assert calls == [
        ("initialize_database",),
        ("handle_delete_details",),
        ("handle_csv_export",),
        ("search_books", ["Python", "Testing"], "stacked"),
    ]
