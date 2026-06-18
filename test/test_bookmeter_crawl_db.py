import logging
from argparse import Namespace

import pytest
from sqlalchemy import create_engine, inspect

import bookmeter_crawl


def db_check_args(**overrides):
    values = {
        "checkread": False,
        "checkstacked": False,
        "checkdetail": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_get_urls_for_detail_crawl_returns_sorted_unique_missing_detail_urls(db_session_factory, add_books):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-missing",
                    "title": "Read missing",
                    "authors": "Author A",
                    "date": "2026/01/01",
                    "url": "https://bookmeter.com/books/30",
                },
            ),
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "shared-missing",
                    "title": "Shared read",
                    "authors": "Author B",
                    "date": "2026/01/02",
                    "url": "https://bookmeter.com/books/20",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "book_id": "stacked-missing",
                    "title": "Stacked missing",
                    "authors": "Author C",
                    "date": None,
                    "url": "https://bookmeter.com/books/10",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "book_id": "shared-missing",
                    "title": "Shared stacked",
                    "authors": "Author B",
                    "date": None,
                    "url": "https://bookmeter.com/books/20",
                },
            ),
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-with-detail",
                    "title": "Read with detail",
                    "authors": "Author D",
                    "date": "2026/01/03",
                    "url": "https://bookmeter.com/books/40",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {
                    "book_id": "read-with-detail",
                    "title": "Read with detail full title",
                    "pages": "200",
                    "amazon_url": "https://www.amazon.co.jp/dp/1234567890",
                    "asin": "1234567890",
                },
            ),
        ],
    )
    session.close()

    urls = bookmeter_crawl.get_urls_for_detail_crawl()

    assert urls == [
        "https://bookmeter.com/books/10",
        "https://bookmeter.com/books/20",
        "https://bookmeter.com/books/30",
    ]


def test_handle_delete_details_removes_only_orphan_details(db_session_factory, add_books):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-linked",
                    "title": "Read linked",
                    "authors": "Author A",
                    "date": "2026/01/01",
                    "url": "https://bookmeter.com/books/1",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "book_id": "stacked-linked",
                    "title": "Stacked linked",
                    "authors": "Author B",
                    "date": None,
                    "url": "https://bookmeter.com/books/2",
                },
            ),
            (bookmeter_crawl.BookDetail, {"book_id": "read-linked", "title": "Keep read"}),
            (bookmeter_crawl.BookDetail, {"book_id": "stacked-linked", "title": "Keep stacked"}),
            (bookmeter_crawl.BookDetail, {"book_id": "orphan", "title": "Delete me"}),
        ],
    )
    session.close()

    bookmeter_crawl.handle_delete_details()

    session = db_session_factory()
    remaining_ids = {
        row.book_id for row in session.query(bookmeter_crawl.BookDetail).order_by(bookmeter_crawl.BookDetail.book_id)
    }
    session.close()

    assert remaining_ids == {"read-linked", "stacked-linked"}


def test_handle_delete_details_keeps_data_when_no_orphan_exists(
    db_session_factory, add_books
):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "linked-detail",
                    "title": "Linked book",
                    "authors": "Author A",
                    "date": "2026/01/01",
                    "url": "https://bookmeter.com/books/linked-detail",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "linked-detail", "title": "Linked detail"},
            ),
        ],
    )
    session.close()

    bookmeter_crawl.handle_delete_details()

    session = db_session_factory()
    remaining_ids = {
        row.book_id for row in session.query(bookmeter_crawl.BookDetail).all()
    }
    session.close()
    assert remaining_ids == {"linked-detail"}


def test_handle_db_checks_prints_lists_and_linked_details(
    db_session_factory, add_books, capsys
):
    session = db_session_factory()
    add_books(
        session,
        [
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-linked",
                    "title": "Read linked",
                    "authors": "Author A",
                    "date": "2026/01/01",
                    "url": "https://bookmeter.com/books/read-linked",
                },
            ),
            (
                bookmeter_crawl.ReadBooks,
                {
                    "book_id": "read-without-detail",
                    "title": "Read without detail",
                    "authors": "Author B",
                    "date": "2026/01/02",
                    "url": "https://bookmeter.com/books/read-without-detail",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "book_id": "stacked-linked",
                    "title": "Stacked linked",
                    "authors": "Author C",
                    "date": None,
                    "url": "https://bookmeter.com/books/stacked-linked",
                },
            ),
            (
                bookmeter_crawl.StackedBooks,
                {
                    "book_id": "stacked-without-detail",
                    "title": "Stacked without detail",
                    "authors": "Author D",
                    "date": None,
                    "url": "https://bookmeter.com/books/stacked-without-detail",
                },
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "read-linked", "title": "Read detail"},
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "stacked-linked", "title": "Stacked detail"},
            ),
            (
                bookmeter_crawl.BookDetail,
                {"book_id": "detail-only", "title": "Detail only"},
            ),
        ],
    )
    session.close()

    bookmeter_crawl.handle_db_checks(
        db_check_args(checkread=True, checkstacked=True, checkdetail=True)
    )

    lines = capsys.readouterr().out.splitlines()
    assert sum(line.startswith("<ReadBooks") for line in lines) == 2
    assert sum(line.startswith("<StackedBooks") for line in lines) == 2
    assert sum(line.startswith("  └ <BookDetail") for line in lines) == 2
    assert sum(line.startswith("<BookDetail") for line in lines) == 3
    assert any("book_id='read-without-detail'" in line for line in lines)
    assert any("book_id='stacked-without-detail'" in line for line in lines)
    assert any("book_id='detail-only'" in line for line in lines)


def test_handle_db_checks_reports_empty_tables(db_session_factory, capsys, caplog):
    with caplog.at_level(logging.INFO, logger="bookmeter_crawl"):
        bookmeter_crawl.handle_db_checks(
            db_check_args(checkread=True, checkstacked=True, checkdetail=True)
        )

    assert capsys.readouterr().out == ""
    messages = [record.getMessage() for record in caplog.records]
    assert "積読本リストにデータはありません。" in messages
    assert "読んだ本リストにデータはありません。" in messages
    assert "書籍詳細にデータはありません。" in messages


def test_session_scope_rolls_back_when_exception_is_raised(db_session_factory):
    with pytest.raises(RuntimeError):
        with bookmeter_crawl.session_scope() as session:
            session.add(
                bookmeter_crawl.ReadBooks(
                    book_id="rollback-target",
                    title="Rollback target",
                    authors="Author A",
                    date="2026/01/01",
                    url="https://bookmeter.com/books/99",
                )
            )
            raise RuntimeError("force rollback")

    session = db_session_factory()
    assert session.query(bookmeter_crawl.ReadBooks).count() == 0
    session.close()


def test_initialize_database_creates_missing_database_file(tmp_path, monkeypatch):
    db_path = tmp_path / "created_by_initialize.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(bookmeter_crawl, "_db_path", db_path)
    monkeypatch.setattr(bookmeter_crawl, "engine", engine)

    bookmeter_crawl.initialize_database()

    assert db_path.exists()
    assert set(inspect(engine).get_table_names()) >= {
        "read_books",
        "stacked_books",
        "book_detail",
    }



def test_initialize_database_does_not_recreate_existing_database(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "existing.db"
    original_content = b"existing database"
    db_path.write_bytes(original_content)
    create_all_calls = []
    monkeypatch.setattr(bookmeter_crawl, "_db_path", db_path)
    monkeypatch.setattr(
        bookmeter_crawl.Base.metadata,
        "create_all",
        lambda engine: create_all_calls.append(engine),
    )

    bookmeter_crawl.initialize_database()

    assert create_all_calls == []
    assert db_path.read_bytes() == original_content
