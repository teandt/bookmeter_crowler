import csv
import logging

import pytest

import bookmeter_crawl


@pytest.fixture
def csv_workdir(tmp_path, monkeypatch):
    (tmp_path / "csv").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def read_booklog_csv(path):
    with path.open(newline="", encoding="sjis") as f:
        return list(csv.reader(f))


@pytest.fixture
def search_books_data(db_session_factory, add_books):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-match",
                    "title": "List title A",
                    "authors": "Author A",
                    "date": "2026/01/03",
                    "url": "https://bookmeter.com/books/read-match",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "book_id": "stacked-match",
                    "title": "List title B",
                    "authors": "Author B",
                    "date": None,
                    "url": "https://bookmeter.com/books/stacked-match",
                },
            ),
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "partial-match",
                    "title": "List title C",
                    "authors": "Author C",
                    "date": "2026/01/04",
                    "url": "https://bookmeter.com/books/partial-match",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "read-match", "title": "Python Testing Guide", "asin": "4444444444"},
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "stacked-match", "title": "Python Testing Practice", "asin": "5555555555"},
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "partial-match", "title": "Python Cookbook", "asin": "7777777777"},
            ),
        ],
    )
    session.close()


def test_handle_csv_export_does_not_write_csv_when_detail_is_missing(db_session_factory, csv_workdir, add_books):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "missing-detail",
                    "title": "Missing detail",
                    "authors": "Author A",
                    "date": "2026/01/01",
                    "url": "https://bookmeter.com/books/1",
                },
            )
        ],
    )
    session.close()

    bookmeter_crawl.handle_csv_export()

    assert not (csv_workdir / "csv" / "booklog.csv").exists()


def test_handle_csv_export_does_not_write_csv_when_asin_is_missing(
    db_session_factory, csv_workdir, add_books, caplog
):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-without-asin",
                    "title": "Read without ASIN",
                    "authors": "Author A",
                    "date": "2026/01/01",
                    "url": "https://bookmeter.com/books/read-without-asin",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "book_id": "stacked-without-asin",
                    "title": "Stacked without ASIN",
                    "authors": "Author B",
                    "date": None,
                    "url": "https://bookmeter.com/books/stacked-without-asin",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "read-without-asin", "title": "Read detail", "asin": None},
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "stacked-without-asin", "title": "Stacked detail", "asin": ""},
            ),
        ],
    )
    session.close()

    with caplog.at_level(logging.ERROR, logger="bookmeter_crawl"):
        bookmeter_crawl.handle_csv_export()

    assert not (csv_workdir / "csv" / "booklog.csv").exists()
    messages = [record.getMessage() for record in caplog.records]
    assert "読んだ本リストで 1 件のASINがありません。" in messages
    assert "積読本リストで 1 件のASINがありません。" in messages


def test_handle_csv_export_writes_empty_csv_when_database_is_empty(
    db_session_factory, csv_workdir
):
    bookmeter_crawl.handle_csv_export()

    csv_path = csv_workdir / "csv" / "booklog.csv"
    assert csv_path.exists()
    assert read_booklog_csv(csv_path) == []


def test_handle_csv_export_writes_read_and_stacked_rows(db_session_factory, csv_workdir, add_books):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-book",
                    "title": "Read short title",
                    "authors": "Author A",
                    "date": "2026/01/02",
                    "url": "https://bookmeter.com/books/10",
                },
            ),
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "unknown-date-book",
                    "title": "Unknown date short title",
                    "authors": "Author B",
                    "date": "日付不明",
                    "url": "https://bookmeter.com/books/20",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "book_id": "stacked-book",
                    "title": "Stacked short title",
                    "authors": "Author C",
                    "date": None,
                    "url": "https://bookmeter.com/books/30",
                },
            ),
            (bookmeter_crawl.BookDetail, {"book_id": "read-book", "title": "Read full title", "asin": "1111111111"}),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "unknown-date-book", "title": "Unknown date full title", "asin": "2222222222"},
            ),
            (bookmeter_crawl.BookDetail, {"book_id": "stacked-book", "title": "Stacked full title", "asin": "3333333333"}),
        ],
    )
    session.close()

    bookmeter_crawl.handle_csv_export()

    rows = read_booklog_csv(csv_workdir / "csv" / "booklog.csv")

    assert rows == [
        ["1", "1111111111", "", "", "", "読み終わった", "", "", "", "", "2026/01/02"],
        ["1", "2222222222", "", "", "", "読み終わった", "", "", "", "", ""],
        ["1", "3333333333", "", "", "", "積読", "", "", "", "", ""],
    ]


def test_search_books_filters_read_target(search_books_data, capsys):
    bookmeter_crawl.search_books(["Python", "Testing"], target="read")

    output = capsys.readouterr().out
    assert "--- 検索結果：1件 (対象: read) ---" in output
    assert "[読] Python Testing Guide / Author A (2026/01/03) : https://bookmeter.com/books/read-match" in output
    assert "Python Testing Practice" not in output


def test_search_books_filters_stacked_target(search_books_data, capsys):
    bookmeter_crawl.search_books(["Python", "Testing"], target="stacked")

    output = capsys.readouterr().out
    assert "--- 検索結果：1件 (対象: stacked) ---" in output
    assert "[積] Python Testing Practice / Author B : https://bookmeter.com/books/stacked-match" in output
    assert "Python Testing Guide" not in output


def test_search_books_all_target_includes_read_and_stacked(search_books_data, capsys):
    bookmeter_crawl.search_books(["Python", "Testing"], target="all")

    output = capsys.readouterr().out
    assert "--- 検索結果：2件 (対象: all) ---" in output
    assert "[読] Python Testing Guide / Author A (2026/01/03) : https://bookmeter.com/books/read-match" in output
    assert "[積] Python Testing Practice / Author B : https://bookmeter.com/books/stacked-match" in output


def test_search_books_requires_all_keywords(search_books_data, capsys):
    bookmeter_crawl.search_books(["Python", "Guide"], target="all")

    output = capsys.readouterr().out
    assert "--- 検索結果：1件 (対象: all) ---" in output
    assert "Python Testing Guide" in output
    assert "Python Testing Practice" not in output
    assert "Python Cookbook" not in output


def test_search_books_prints_message_when_no_results(db_session_factory, capsys, add_books):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-book",
                    "title": "List title",
                    "authors": "Author A",
                    "date": "2026/01/04",
                    "url": "https://bookmeter.com/books/read-book",
                },
            ),
            (bookmeter_crawl.BookDetail, {"book_id": "read-book", "title": "Completely Different", "asin": "6666666666"}),
        ],
    )
    session.close()

    bookmeter_crawl.search_books(["NoSuchKeyword"], target="all")

    assert capsys.readouterr().out == "該当する書籍は見つかりませんでした。\n"
