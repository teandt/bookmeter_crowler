import re
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request

from cr_bookmeter.spiders.bookmeter_bookdetail import BookmeterBookDetailSpider
from cr_bookmeter.spiders.bookmeter_read import BookmeterReadSpider
from cr_bookmeter.spiders.bookmeter_stacked import BookmeterStackedSpider


def split_parse_results(results):
    items = []
    requests = []
    for result in results:
        if isinstance(result, Request):
            requests.append(result)
        else:
            items.append(dict(result))
    return items, requests


def assert_book_list_item(item, require_authors=True):
    assert re.fullmatch(r"\d+", item["id"])
    assert item["short_title"]
    assert "authors" in item
    if require_authors:
        assert item["authors"]
    assert item["url"] == f"https://bookmeter.com/books/{item['id']}"


def response_from_path(path, url):
    return HtmlResponse(
        url=url,
        body=path.read_bytes(),
        encoding="utf-8",
        request=Request(url=url),
    )


def test_read_spider_parses_saved_read_page_and_next_request(url_for_testdata, response_from_saved_html):
    url = url_for_testdata("page/read/read_1.html")
    next_url = url_for_testdata("page/read/read_2.html")
    spider = BookmeterReadSpider()

    items, requests = split_parse_results(spider.parse(response_from_saved_html(url)))

    assert len(items) > 0
    assert_book_list_item(items[0])
    assert items[0]["date"]
    assert re.fullmatch(r"\d{4}/\d{2}/\d{2}|日付不明", items[0]["date"])
    assert len(requests) == 1
    assert requests[0].url == next_url


def test_stacked_spider_parses_saved_stacked_page_and_next_request(url_for_testdata, response_from_saved_html):
    url = url_for_testdata("page/stacked/stacked_1.html")
    next_url = url_for_testdata("page/stacked/stacked_2.html")
    spider = BookmeterStackedSpider()

    items, requests = split_parse_results(spider.parse(response_from_saved_html(url)))

    assert len(items) > 0
    assert_book_list_item(items[0])
    assert "date" in items[0]
    assert len(requests) == 1
    assert requests[0].url == next_url


def test_book_detail_spider_parses_saved_detail_page(
    url_map, response_from_saved_html
):
    detail_urls = sorted(
        url
        for url, relative_path in url_map.items()
        if relative_path.startswith("page/detail/")
    )
    assert detail_urls
    url = detail_urls[0]
    spider = BookmeterBookDetailSpider()

    items, requests = split_parse_results(spider.parse(response_from_saved_html(url)))

    assert requests == []
    assert len(items) == 1

    item = items[0]
    expected_id = url.rstrip("/").rsplit("/", 1)[-1]
    assert item["id"] == expected_id
    assert re.fullmatch(r"\d+", item["id"])
    assert item["title"]
    assert item["pages"]
    assert item["amazon_url"]
    asin_match = re.search(
        r"/dp/(?:product/)?([A-Z0-9]{10})", item["amazon_url"]
    )
    if asin_match:
        assert item["asin"] == asin_match.group(1)
    else:
        assert "asin" not in item


@pytest.mark.slow
@pytest.mark.parametrize(
    ("directory", "spider_class"),
    [
        ("read", BookmeterReadSpider),
        ("stacked", BookmeterStackedSpider),
    ],
)
def test_all_saved_book_list_pages(
    directory, spider_class, url_map, slow_test_reporter
):
    testdata_root = Path(__file__).parent / "testdata"
    urls_by_path = {path: url for url, path in url_map.items()}
    html_paths = sorted((testdata_root / "page" / directory).glob("*.html"))

    assert html_paths
    last_page_number = max(
        int(html_path.stem.rsplit("_", 1)[1]) for html_path in html_paths
    )
    item_count = 0
    for html_path in html_paths:
        relative_path = html_path.relative_to(testdata_root).as_posix()
        url = urls_by_path[relative_path]
        items, requests = split_parse_results(
            spider_class().parse(response_from_path(html_path, url))
        )

        assert items, relative_path
        item_count += len(items)
        for item in items:
            assert_book_list_item(item, require_authors=False)
            assert item["authors"] is None or item["authors"].strip()
            assert "date" in item
        page_number = int(html_path.stem.rsplit("_", 1)[1])
        assert len(requests) == (page_number < last_page_number), relative_path

    slow_test_reporter(directory, len(html_paths), item_count)


@pytest.mark.slow
def test_all_saved_book_detail_pages(slow_test_reporter):
    detail_directory = Path(__file__).parent / "testdata" / "page" / "detail"
    html_paths = sorted(detail_directory.glob("detail_*.html"))

    assert html_paths
    spider = BookmeterBookDetailSpider()
    for html_path in html_paths:
        book_id = html_path.stem.removeprefix("detail_")
        url = f"https://bookmeter.com/books/{book_id}"
        items, requests = split_parse_results(
            spider.parse(response_from_path(html_path, url))
        )

        assert requests == [], html_path.name
        assert len(items) == 1, html_path.name
        item = items[0]
        assert item["id"] == book_id
        assert item["title"], html_path.name
        assert item["pages"], html_path.name
        assert item["amazon_url"], html_path.name
        asin_match = re.search(
            r"/dp/(?:product/)?([A-Z0-9]{10})", item["amazon_url"]
        )
        if asin_match:
            assert item["asin"] == asin_match.group(1), html_path.name
        else:
            assert "asin" not in item, html_path.name

    slow_test_reporter("detail", len(html_paths), len(html_paths))
