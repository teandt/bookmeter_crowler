import scrapy
from dotenv import dotenv_values
from cr_bookmeter.items import CrBookmeterItem
from scrapy_splash import SplashRequest
from . import lua_scripts

class BookmeterReadSpider(scrapy.Spider):
    env = dotenv_values("./env/.env")
    name = "bookmeter_read"
    allowed_domains = ["bookmeter.com", "localhost"]
    custom_settings = {
        'FEED_URI': 'output_read.json',
        'FEED_FORMAT': 'json',
        'FEED_EXPORT_ENCODING': 'utf-8',
    }

    def start_requests(self):
        url = "https://bookmeter.com/users/{}".format(self.env["USER_ID"])+"/books/read"
        yield SplashRequest(
            url, self.parse, endpoint='execute',
            args={
                'lua_source': lua_scripts.BOOKMETER_LUA_SCRIPT,
                'wait_for_selector': 'ul.content-list--book',
                'timeout': 90,
            }
        )

    def parse(self, response):
        books = response.xpath('//li[@class="group__book"]')

        for book in books:
            bookinfo = CrBookmeterItem()

            href = book.xpath('.//div[@class="book__thumbnail"]/div[@class="thumbnail__cover"]/a/@href').get()

            if not href:
                self.logger.warning(f"Could not find href for a book on page {response.url}")
                continue

            bookinfo["id"] = href.split('/')[-1]
            
            bookinfo["short_title"] = book.xpath('.//div[@class="detail__title"]//a/text()').get()
            bookinfo["authors"] = book.xpath('.//ul[@class="detail__authors"]//a/text()').get()
            bookinfo["date"] = book.xpath('.//div[@class="detail__date"]//text()').get()
            bookinfo["url"] = "https://bookmeter.com" + href
            
            yield bookinfo
        
        next_page = response.xpath('//ul[@class="bm-pagination"]//a[@rel="next"]/@href').get()
        if next_page is not None:
            yield SplashRequest(
                response.urljoin(next_page), self.parse, endpoint='execute',
                args={
                    'lua_source': lua_scripts.BOOKMETER_LUA_SCRIPT,
                    'wait_for_selector': 'ul.content-list--book',
                    'timeout': 90,
                }
            )
