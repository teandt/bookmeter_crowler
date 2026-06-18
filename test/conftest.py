import json
import os
import sys
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[1]
CRAWLER_ROOT = REPO_ROOT / "cr_bookmeter"
TESTDATA_ROOT = REPO_ROOT / "test" / "testdata"

sys.path.insert(0, str(CRAWLER_ROOT))

_original_cwd = os.getcwd()
os.chdir(CRAWLER_ROOT)
try:
    import bookmeter_crawl
finally:
    os.chdir(_original_cwd)


@pytest.fixture
def db_session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'bookmeter_test.db'}")
    bookmeter_crawl.Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)
    monkeypatch.setattr(bookmeter_crawl, "Session", test_session)
    return test_session


@pytest.fixture
def add_books():
    def add(session, rows):
        for model, values in rows:
            session.add(model(**values))
        session.commit()

    return add


@pytest.fixture(scope="session")
def url_map():
    with (TESTDATA_ROOT / "url_map.json").open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def url_for_testdata(url_map):
    def find_url(relative_path):
        matches = [
            url
            for url, mapped_path in url_map.items()
            if mapped_path == relative_path
        ]
        assert len(matches) == 1, f"Expected one URL for {relative_path}, found {matches}"
        return matches[0]

    return find_url


@pytest.fixture
def response_from_saved_html(url_map):
    def build_response(url):
        html_path = TESTDATA_ROOT / url_map[url]
        return HtmlResponse(
            url=url,
            body=html_path.read_bytes(),
            encoding="utf-8",
            request=Request(url=url),
        )

    return build_response


@pytest.fixture
def slow_test_reporter(pytestconfig):
    def report(category, html_count, item_count):
        pytestconfig._slow_test_results[category] = (html_count, item_count)

    return report


def pytest_configure(config):
    config._slow_test_results = {}


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not config._slow_test_results:
        return

    terminalreporter.section("slow test summary")
    for category in ("read", "stacked", "detail"):
        result = config._slow_test_results.get(category)
        if result is None:
            continue
        html_count, item_count = result
        terminalreporter.write_line(
            f"[slow] {category}: "
            f"{html_count} HTML files checked, {item_count} items parsed"
        )
