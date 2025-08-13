import scrapy
import re
from dotenv import dotenv_values
from cr_bookmeter.items import CrBookmeterItem

class BookmeterSpider(scrapy.Spider):
    env = dotenv_values("./env/.env")
    name = "bookmeter"
    allowed_domains = ["bookmeter.com"]
    start_urls = ["https://bookmeter.com/users/{}".format(env["USER_ID"])+"/books/read"]

    def detail_parse(self, response):
        bookinfo = response.meta["bookinfo"]
        bookinfo["amazon_url"] = response.xpath('//div[@class="bm-wrapper"]//div[@class="group__image"]/a/@href').get()

        match = re.search(r'/dp/(?:product/)?([A-Z0-9]{10})', bookinfo["amazon_url"])
        if(match):
            bookinfo["asin"] = match.group(1)

        yield bookinfo


    def parse(self, response):
        books = response.xpath('//li[@class="group__book"]')

        for book in books:
            bookinfo = CrBookmeterItem()

            href = book.xpath('.//div[@class="book__thumbnail"]/div[@class="thumbnail__cover"]/a/@href').get()

            bookinfo["id"] = href.split('/')[-1]
            bookinfo["title"] = book.xpath('.//div[@class="detail__title"]//a/text()').get()
            bookinfo["author"] = book.xpath('.//ul[@class="detail__authors"]//a/text()').get()
            bookinfo["date"] = book.xpath('.//div[@class="detail__date"]//text()').get()
            bookinfo["url"] = "https://bookmeter.com" + href
            
            yield response.follow(url=bookinfo["url"], callback=self.detail_parse, meta={"bookinfo": bookinfo})
            
            yield bookinfo
        
        next_page = response.xpath('//ul[@class="bm-pagination"]//a[@rel="next"]/@href').get()
        if next_page is not None:
            yield response.follow(url=next_page, callback=self.parse)


