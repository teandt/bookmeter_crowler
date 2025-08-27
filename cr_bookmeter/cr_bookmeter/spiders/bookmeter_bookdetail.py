import scrapy
import re
from dotenv import dotenv_values
from cr_bookmeter.items import CrBookmeterDetailItem
from scrapy_splash import SplashRequest
from . import lua_scripts

class BookmeterBookDetailSpider(scrapy.Spider):
    env = dotenv_values("./env/.env")
    name = "bookmeter_bookdetail"
    allowed_domains = ["bookmeter.com", "localhost"]
    custom_settings = {
        'FEED_URI': 'output_details.json',
        'FEED_FORMAT': 'json',
        'FEED_EXPORT_ENCODING': 'utf-8',
    }

    def __init__(self, target_urls=None, *args, **kwargs):
        """
        コンストラクタ。CrawlerProcessから引数を受け取ります。
        """
        super().__init__(*args, **kwargs)
        # 実行スクリプトからURLリストを受け取り、start_urlsに設定
        if target_urls:
            self.start_urls = target_urls
        # -a url=... で単一URLが渡された場合も考慮
        elif hasattr(self, 'url'):
            self.start_urls = [self.url]
        else:
            self.start_urls = []

    def start_requests(self):
        if not self.start_urls:
            self.logger.info("No target URLs provided for book details.")
            return

        for url in self.start_urls:
            yield SplashRequest(
                url,
                self.parse,
                endpoint='execute',
                args={
                    'lua_source': lua_scripts.BOOKMETER_LUA_SCRIPT,
                    'wait_for_selector': 'h1.inner__title',
                    'timeout': 90,
                }
            )

    def parse(self, response):
        '''
        個別の書籍ページから詳細情報を取得
        '''
        detail_item = CrBookmeterDetailItem()

        detail_item["id"] = response.url.split('/')[-1]
        detail_item["title"] = response.xpath('//h1[@class="inner__title"]/text()').get()
        # TODO: ページ数のXPathを特定して実装
        detail_item["pages"] = response.xpath('//section[contains(@class, "books show")]//section[contains(@class, "sidebar__group")]//section[contains(@class, "group__detail")]//dd[@class="bm-details-side__item"][2]/span[1]/text()').get()
        # detail_item["pages"] = response.xpath('...').get()

        amazon_url = response.xpath('//div[@class="bm-wrapper"]//div[@class="group__image"]/a/@href').get()
        detail_item["amazon_url"] = amazon_url

        if amazon_url:
            match = re.search(r'/dp/(?:product/)?([A-Z0-9]{10})', amazon_url)
            if match:
                detail_item["asin"] = match.group(1)

        yield detail_item
