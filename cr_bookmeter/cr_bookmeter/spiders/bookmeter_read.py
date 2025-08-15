import scrapy
from dotenv import dotenv_values
from cr_bookmeter.items import CrBookmeterItem

class BookmeterReadSpider(scrapy.Spider):
    env = dotenv_values("./env/.env")
    name = "bookmeter_read"
    allowed_domains = ["bookmeter.com"]
    start_urls = ["https://bookmeter.com/users/{}".format(env["USER_ID"])+"/books/read"]

    def parse(self, response):
        books = response.xpath('//li[@class="group__book"]')

        for book in books:
            bookinfo = CrBookmeterItem()

            href = book.xpath('.//div[@class="book__thumbnail"]/div[@class="thumbnail__cover"]/a/@href').get()

            bookinfo["id"] = href.split('/')[-1]
            
            #取得するタイトルは長いと欠落する短縮版。 あとの個別書籍ページ参照で上書きする
            bookinfo["short_title"] = book.xpath('.//div[@class="detail__title"]//a/text()').get()
            bookinfo["author"] = book.xpath('.//ul[@class="detail__authors"]//a/text()').get()
            bookinfo["date"] = book.xpath('.//div[@class="detail__date"]//text()').get()
            bookinfo["url"] = "https://bookmeter.com" + href
            
            yield bookinfo
        
        next_page = response.xpath('//ul[@class="bm-pagination"]//a[@rel="next"]/@href').get()
        if next_page is not None:
            yield response.follow(url=next_page, callback=self.parse)
