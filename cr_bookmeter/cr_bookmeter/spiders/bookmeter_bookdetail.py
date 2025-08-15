import scrapy
import re
from dotenv import dotenv_values
from cr_bookmeter.items import CrBookmeterItem

class BookmeterBookDetailSpider(scrapy.Spider):
    env = dotenv_values("./env/.env")
    name = "bookmeter_bookdetail"
    allowed_domains = ["bookmeter.com"]
    # start_urlsは使わないので削除し、start_requestsメソッドを実装します

    def start_requests(self):
        """
        クロールの開始リクエストを生成します。
        -a url="..." のように引数が渡された場合はそのURLを、
        渡されなかった場合はデフォルトのURLを使用します。
        """
        # getattrで引数を取得します。引数がなければNoneが返ります。
        target_url = getattr(self, 'url', None)

        if target_url:
            yield scrapy.Request(target_url, callback=self.parse)
        else:
            # 引数が指定されなかった場合エラー
            self.logger.error(f"No URL provided via '-a url=...'")
            exit()
            
    def parse(self, response):
        '''
        個別の書籍ページから詳細情報を取得
        Item情報はmeta={"bookinfo": bookinfo}で指定
        '''
        
        bookinfo = response.meta["bookinfo"]
        
        #タイトルは個別書籍ページから参照しないと長い場合欠落してしまうため取り直し
        bookinfo["title"] = response.xpath('//section[contains(@class, "books show")]/header[@class="show__header"]//h1[@class="inner__title"]/text()').get()
        amazon_url = response.xpath('//div[@class="bm-wrapper"]//div[@class="group__image"]/a/@href').get()
        bookinfo["amazon_url"] = amazon_url

        if amazon_url:
            match = re.search(r'/dp/(?:product/)?([A-Z0-9]{10})', amazon_url)
            if match:
                bookinfo["asin"] = match.group(1)

        yield bookinfo
