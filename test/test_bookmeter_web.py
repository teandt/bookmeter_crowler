import io
import json
import logging
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

import bookmeter_crawl
import bookmeter_web


def add_web_test_data(db_session_factory, add_books):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "num": 2,
                    "book_id": "read-linked",
                    "title": "Read list title",
                    "authors": "Read author",
                    "date": "2026/07/01",
                    "url": "https://bookmeter.com/books/read-linked",
                },
            ),
            (
                bookmeter_crawl.ReadBooks,
                {
                    "num": 1,
                    "book_id": "read-missing-detail",
                    "title": "Missing detail",
                    "authors": None,
                    "date": None,
                    "url": None,
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "num": 1,
                    "book_id": "stacked-linked",
                    "title": "Stacked list title",
                    "authors": "Stacked author",
                    "date": None,
                    "url": "https://bookmeter.com/books/stacked-linked",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "num": 2,
                    "book_id": "stacked-no-asin",
                    "title": "No ASIN",
                    "authors": "Another author",
                    "date": None,
                    "url": "https://bookmeter.com/books/stacked-no-asin",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {
                    "book_id": "read-linked",
                    "title": "Series IX",
                    "pages": "320",
                    "amazon_url": "https://www.amazon.co.jp/dp/1111111111",
                    "asin": "1111111111",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {
                    "book_id": "stacked-linked",
                    "title": "Series X",
                    "pages": None,
                    "amazon_url": None,
                    "asin": "2222222222",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {
                    "book_id": "stacked-no-asin",
                    "title": "Series V",
                    "asin": "",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {
                    "book_id": "orphan",
                    "title": "Orphan detail",
                    "asin": "3333333333",
                },
            ),
        ],
    )
    session.close()


@pytest.fixture(autouse=True)
def isolate_job_manager(monkeypatch):
    monkeypatch.setattr(bookmeter_web, "JOB_MANAGER", bookmeter_web.JobManager())


def test_make_crawl_args_handles_individual_and_all_options():
    args = bookmeter_web.make_crawl_args({"stacked": True, "detail": True})

    assert vars(args) == {
        "stacked": True,
        "read": False,
        "detail": True,
        "all": False,
        "checkstacked": False,
        "checkread": False,
        "checkdetail": False,
        "deletedetail": False,
        "csv": False,
        "search": None,
        "target": "all",
    }

    all_args = bookmeter_web.make_crawl_args({"all": True})
    assert all_args.all is True
    assert (all_args.stacked, all_args.read, all_args.detail) == (True, True, True)


def test_make_crawl_args_rejects_empty_selection():
    with pytest.raises(ValueError, match="少なくとも1つ"):
        bookmeter_web.make_crawl_args({})


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, ""), (0, 0), ("title", "title")],
)
def test_row_value(value, expected):
    assert bookmeter_web.row_value(value) == expected


def test_detail_and_list_entry_conversion():
    detail = SimpleNamespace(
        book_id="book-1",
        title=None,
        pages="200",
        amazon_url=None,
        asin="1234567890",
    )
    entry = SimpleNamespace(
        num=3,
        book_id="book-1",
        title="List title",
        authors=None,
        date=None,
        url="https://bookmeter.com/books/book-1",
    )

    assert bookmeter_web.detail_to_dict(None) is None
    assert bookmeter_web.list_entry_to_dict(entry, detail) == {
        "num": 3,
        "book_id": "book-1",
        "title": "List title",
        "authors": "",
        "date": "",
        "url": "https://bookmeter.com/books/book-1",
        "detail": {
            "book_id": "book-1",
            "title": "",
            "pages": "200",
            "amazon_url": "",
            "asin": "1234567890",
        },
    }
    assert bookmeter_web.list_entry_to_dict(entry, label="読")["label"] == "読"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("IX", 9), ("XIV", 14), ("MCMXCIV", 1994), ("A", 0)],
)
def test_roman_to_int(text, expected):
    assert bookmeter_web.roman_to_int(text) == expected


def test_natural_keys_recognizes_numbers_and_supported_roman_numerals():
    titles = ["Book 2", "Book 10", "Series IX", "Series V", "SIX", "SIV"]

    assert sorted(titles, key=bookmeter_web.natural_keys) == [
        "Book 2",
        "Book 10",
        "SIV",
        "SIX",
        "Series V",
        "Series IX",
    ]


@pytest.mark.parametrize("kind", ["read", "stacked", "detail"])
def test_get_books_returns_requested_database_rows(kind, db_session_factory, add_books):
    add_web_test_data(db_session_factory, add_books)

    result = bookmeter_web.get_books(kind)

    assert result["kind"] == kind
    if kind == "read":
        assert [item["book_id"] for item in result["items"]] == [
            "read-missing-detail",
            "read-linked",
        ]
        assert result["items"][0]["detail"] is None
        assert result["items"][1]["label"] == "読"
    elif kind == "stacked":
        assert [item["label"] for item in result["items"]] == ["積", "積"]
    else:
        assert [item["title"] for item in result["items"]] == [
            "Orphan detail",
            "Series IX",
            "Series V",
            "Series X",
        ]
    assert result["count"] == len(result["items"])


def test_get_books_rejects_unknown_kind(db_session_factory):
    with pytest.raises(ValueError, match="read, stacked, detail"):
        bookmeter_web.get_books("unknown")


def test_search_books_filters_by_target_and_all_keywords(db_session_factory, add_books):
    add_web_test_data(db_session_factory, add_books)

    result = bookmeter_web.search_books(["Series"], "all")
    read_result = bookmeter_web.search_books(["Series", "IX"], "read")

    assert [item["title"] for item in result["items"]] == [
        "Series X",
        "Series IX",
        "Series V",
    ]
    assert {item["label"] for item in result["items"]} == {"読", "積"}
    assert read_result == {
        "target": "read",
        "keywords": ["Series", "IX"],
        "count": 1,
        "items": [
            {
                "label": "読",
                "title": "Series IX",
                "authors": "Read author",
                "date": "2026/07/01",
                "book_id": "read-linked",
                "url": "https://bookmeter.com/books/read-linked",
            }
        ],
    }


@pytest.mark.parametrize(
    ("keywords", "target", "message"),
    [([], "all", "キーワード"), (["Series"], "detail", "target")],
)
def test_search_books_validates_input(keywords, target, message):
    with pytest.raises(ValueError, match=message):
        bookmeter_web.search_books(keywords, target)


def test_preview_and_delete_details_job(db_session_factory, add_books, monkeypatch):
    add_web_test_data(db_session_factory, add_books)

    preview = bookmeter_web.preview_delete_details()
    monkeypatch.setattr(bookmeter_crawl, "handle_delete_details", lambda: None)
    deleted = bookmeter_web.delete_details_job()

    assert preview == {
        "count": 1,
        "items": [
            {
                "book_id": "orphan",
                "title": "Orphan detail",
                "pages": "",
                "amazon_url": "",
                "asin": "3333333333",
            }
        ],
    }
    assert deleted == {"deleted_count": 1, "deleted_items": preview["items"]}


def test_csv_validation_status_reports_each_missing_category(
    db_session_factory, add_books, monkeypatch, tmp_path
):
    add_web_test_data(db_session_factory, add_books)
    csv_path = tmp_path / "booklog.csv"
    monkeypatch.setattr(bookmeter_web, "CSV_PATH", csv_path)

    result = bookmeter_web.csv_validation_status()

    assert result == {
        "valid": False,
        "missing_read_detail": 1,
        "missing_stacked_detail": 0,
        "missing_read_asin": 0,
        "missing_stacked_asin": 1,
        "csv_exists": False,
        "csv_path": str(csv_path),
    }


def test_run_csv_job_initializes_exports_and_reports_file(monkeypatch, tmp_path):
    calls = []
    csv_path = tmp_path / "booklog.csv"
    csv_path.write_text("csv", encoding="utf-8")
    monkeypatch.setattr(bookmeter_web, "CSV_PATH", csv_path)
    monkeypatch.setattr(bookmeter_crawl, "initialize_database", lambda: calls.append("init"))
    monkeypatch.setattr(bookmeter_crawl, "handle_csv_export", lambda: calls.append("export"))

    assert bookmeter_web.run_csv_job() == {"path": str(csv_path), "exists": True}
    assert calls == ["init", "export"]


class FakeProcess:
    def __init__(self, return_code):
        self.stdout = iter(["first line\n", "second line\n"])
        self.return_code = return_code

    def wait(self):
        return self.return_code


def test_run_crawl_job_builds_cli_command_and_collects_output(monkeypatch, caplog):
    calls = []

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess(0)

    monkeypatch.setattr(bookmeter_crawl, "initialize_database", lambda: calls.append("init"))
    monkeypatch.setattr(bookmeter_web.subprocess, "Popen", fake_popen)

    with caplog.at_level(logging.INFO, logger="bookmeter_crawl"):
        result = bookmeter_web.run_crawl_job({"stacked": True, "read": True, "detail": True})

    assert result == {"stacked": True, "read": True, "detail": True}
    assert calls[0] == "init"
    assert calls[1][0] == [
        sys.executable,
        str(bookmeter_web.BASE_DIR / "bookmeter_crawl.py"),
        "--stacked",
        "--read",
        "--detail",
    ]
    assert calls[1][1]["cwd"] == bookmeter_web.BASE_DIR
    assert "first line" in [record.getMessage() for record in caplog.records]


def test_run_crawl_job_uses_all_flag_and_raises_for_failure(monkeypatch):
    captured = {}
    monkeypatch.setattr(bookmeter_crawl, "initialize_database", lambda: None)

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return FakeProcess(7)

    monkeypatch.setattr(bookmeter_web.subprocess, "Popen", fake_popen)

    with pytest.raises(RuntimeError, match="終了コード: 7"):
        bookmeter_web.run_crawl_job({"all": True})

    assert captured["command"][-1] == "--all"


class ImmediateThread:
    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


def test_job_manager_records_success_and_logs(monkeypatch):
    monkeypatch.setattr(bookmeter_web.threading, "Thread", ImmediateThread)
    manager = bookmeter_web.JobManager()

    snapshot = manager.start("成功処理", lambda: {"count": 2})
    status = manager.status()

    assert snapshot["status"] == "succeeded"
    assert status["running"] is False
    assert status["job"]["result"] == {"count": 2}
    assert status["job"]["started_at"]
    assert status["job"]["finished_at"]
    assert status["job"]["logs"][0] == "成功処理 を開始しました。"
    assert status["job"]["logs"][-1] == "成功処理 を終了しました。"


def test_job_manager_records_failure_and_rejects_parallel_job(monkeypatch):
    monkeypatch.setattr(bookmeter_web.threading, "Thread", ImmediateThread)
    manager = bookmeter_web.JobManager()

    def fail():
        raise ValueError("boom")

    snapshot = manager.start("失敗処理", fail)

    assert snapshot["status"] == "failed"
    assert snapshot["error"] == "boom"
    assert any("ValueError: boom" in line for line in snapshot["logs"])

    manager.current = bookmeter_web.Job("実行中")
    manager.current.status = "running"
    with pytest.raises(RuntimeError, match="別の処理が実行中"):
        manager.start("次の処理", lambda: None)


def test_job_log_handler_ignores_log_storage_failure():
    job = SimpleNamespace(add_log=lambda message: (_ for _ in ()).throw(RuntimeError("boom")))
    handler = bookmeter_web.JobLogHandler(job)

    handler.emit(logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None))


def make_handler(path="/"):
    handler = object.__new__(bookmeter_web.WebHandler)
    handler.path = path
    handler.headers = {}
    handler.rfile = io.BytesIO()
    handler.wfile = io.BytesIO()
    handler.responses = []
    handler.response_headers = []
    handler.send_response = lambda status: handler.responses.append(status)
    handler.send_header = lambda name, value: handler.response_headers.append((name, value))
    handler.end_headers = lambda: None
    return handler


def captured_dispatch(path, method="GET"):
    handler = make_handler(path)
    captured = []
    handler.send_json = lambda data, status=HTTPStatus.OK: captured.append((data, status))
    handler.send_html = lambda html: captured.append((html, HTTPStatus.OK))
    handler.send_csv = lambda: captured.append(("csv", HTTPStatus.OK))
    handler.dispatch(method)
    return captured


def test_dispatch_get_routes(monkeypatch):
    monkeypatch.setattr(bookmeter_web.JOB_MANAGER, "status", lambda: {"running": False, "job": None})
    monkeypatch.setattr(bookmeter_web, "csv_validation_status", lambda: {"valid": True})
    monkeypatch.setattr(bookmeter_web, "get_books", lambda kind: {"kind": kind})
    monkeypatch.setattr(
        bookmeter_web,
        "search_books",
        lambda keywords, target: {"keywords": keywords, "target": target},
    )
    monkeypatch.setattr(bookmeter_web, "preview_delete_details", lambda: {"count": 0})

    assert captured_dispatch("/")[0][0] == bookmeter_web.INDEX_HTML
    assert captured_dispatch("/api/status") == [({"running": False, "job": None}, HTTPStatus.OK)]
    assert captured_dispatch("/api/csv/status") == [({"valid": True}, HTTPStatus.OK)]
    assert captured_dispatch("/api/download/csv") == [("csv", HTTPStatus.OK)]
    assert captured_dispatch("/api/books?kind=stacked") == [({"kind": "stacked"}, HTTPStatus.OK)]
    assert captured_dispatch("/api/books") == [({"kind": "read"}, HTTPStatus.OK)]
    assert captured_dispatch("/api/search?q=one%20two&target=read") == [
        ({"keywords": ["one", "two"], "target": "read"}, HTTPStatus.OK)
    ]
    assert captured_dispatch("/api/delete-details/preview") == [({"count": 0}, HTTPStatus.OK)]


def test_dispatch_post_routes(monkeypatch):
    calls = []

    def fake_start(name, target):
        calls.append((name, target))
        return {"name": name}

    monkeypatch.setattr(bookmeter_web.JOB_MANAGER, "start", fake_start)
    run_handler = make_handler("/api/run")
    run_handler.read_json = lambda: {"read": True}
    run_responses = []
    run_handler.send_json = lambda data, status=HTTPStatus.OK: run_responses.append((data, status))
    run_handler.dispatch("POST")

    assert run_responses == [({"name": "クロール"}, HTTPStatus.ACCEPTED)]
    assert calls[0][0] == "クロール"
    monkeypatch.setattr(bookmeter_web, "run_crawl_job", lambda payload: payload)
    assert calls[0][1]() == {"read": True}

    assert captured_dispatch("/api/csv", "POST") == [
        ({"name": "CSV出力"}, HTTPStatus.ACCEPTED)
    ]
    assert captured_dispatch("/api/delete-details", "POST") == [
        ({"name": "不要詳細データ削除"}, HTTPStatus.ACCEPTED)
    ]


@pytest.mark.parametrize(
    ("exception", "status"),
    [
        (ValueError("bad input"), HTTPStatus.BAD_REQUEST),
        (RuntimeError("busy"), HTTPStatus.CONFLICT),
        (OSError("broken"), HTTPStatus.INTERNAL_SERVER_ERROR),
    ],
)
def test_dispatch_maps_exceptions_to_http_status(monkeypatch, exception, status):
    monkeypatch.setattr(bookmeter_web, "get_books", lambda kind: (_ for _ in ()).throw(exception))

    assert captured_dispatch("/api/books") == [({"error": str(exception)}, status)]


def test_dispatch_returns_not_found():
    assert captured_dispatch("/unknown") == [({"error": "Not Found"}, HTTPStatus.NOT_FOUND)]


def test_handler_delegates_http_methods_and_logs(monkeypatch):
    handler = make_handler("/")
    calls = []
    handler.dispatch = lambda method: calls.append(method)
    handler.address_string = lambda: "127.0.0.1"
    monkeypatch.setattr(bookmeter_web.logger, "info", lambda *args: calls.append(args))

    handler.do_GET()
    handler.do_POST()
    handler.log_message("status %s", 200)

    assert calls[:2] == ["GET", "POST"]
    assert calls[2][1:] == ("127.0.0.1", "status 200")


def test_ensure_not_running_rejects_active_job(monkeypatch):
    handler = make_handler()
    monkeypatch.setattr(bookmeter_web.JOB_MANAGER, "status", lambda: {"running": True})

    with pytest.raises(RuntimeError, match="別の処理が実行中"):
        handler.ensure_not_running()


def test_read_json_handles_empty_and_nonempty_body():
    empty = make_handler()
    assert empty.read_json() == {}

    body = json.dumps({"read": True}).encode("utf-8")
    handler = make_handler()
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    assert handler.read_json() == {"read": True}


def test_send_html_and_json_write_headers_and_utf8_body():
    html_handler = make_handler()
    html_handler.send_html("日本語")
    assert html_handler.responses == [HTTPStatus.OK]
    assert ("Content-Type", "text/html; charset=utf-8") in html_handler.response_headers
    assert html_handler.wfile.getvalue().decode("utf-8") == "日本語"

    json_handler = make_handler()
    json_handler.send_json({"message": "日本語"}, HTTPStatus.ACCEPTED)
    assert json_handler.responses == [HTTPStatus.ACCEPTED]
    assert ("Content-Type", "application/json; charset=utf-8") in json_handler.response_headers
    assert json.loads(json_handler.wfile.getvalue()) == {"message": "日本語"}


def test_send_csv_returns_missing_error_or_download(monkeypatch, tmp_path):
    csv_path = tmp_path / "booklog.csv"
    monkeypatch.setattr(bookmeter_web, "CSV_PATH", csv_path)
    missing_handler = make_handler()
    missing = []
    missing_handler.send_json = lambda data, status=HTTPStatus.OK: missing.append((data, status))
    missing_handler.send_csv()

    assert missing == [
        ({"error": "CSVファイルがありません。先にCSV出力を実行してください。"}, HTTPStatus.NOT_FOUND)
    ]

    csv_path.write_bytes(b"csv-body")
    download_handler = make_handler()
    download_handler.send_csv()
    assert download_handler.responses == [HTTPStatus.OK]
    assert ("Content-Type", "text/csv; charset=shift_jis") in download_handler.response_headers
    assert ("Content-Disposition", 'attachment; filename="booklog.csv"') in download_handler.response_headers
    assert download_handler.wfile.getvalue() == b"csv-body"


def test_main_starts_and_closes_server_on_keyboard_interrupt(monkeypatch):
    calls = []

    class FakeServer:
        def __init__(self, address, handler_class):
            calls.append(("init", address, handler_class))

        def serve_forever(self):
            calls.append(("serve_forever",))
            raise KeyboardInterrupt

        def server_close(self):
            calls.append(("server_close",))

    monkeypatch.setattr(sys, "argv", ["bookmeter_web.py", "--host", "0.0.0.0", "--port", "9000"])
    monkeypatch.setattr(bookmeter_web.os, "chdir", lambda path: calls.append(("chdir", path)))
    monkeypatch.setattr(bookmeter_web.logging, "basicConfig", lambda **kwargs: calls.append(("logging", kwargs)))
    monkeypatch.setattr(bookmeter_web, "ThreadingHTTPServer", FakeServer)

    bookmeter_web.main()

    assert ("chdir", bookmeter_web.BASE_DIR) in calls
    assert ("init", ("0.0.0.0", 9000), bookmeter_web.WebHandler) in calls
    assert calls[-2:] == [("serve_forever",), ("server_close",)]
