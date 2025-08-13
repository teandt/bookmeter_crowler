import scrapy
from dotenv import dotenv_values

class BookmeterSpider(scrapy.Spider):
    env = dotenv_values("./env/.env")
    name = "bookmeter"
    allowed_domains = ["bookmeter.com"]
    start_urls = ["https://bookmeter.com/users/{}".format(env["USER_ID"])+"/books/read"]

    def parse(self, response):
        books = response.xpath('//li[@class="group__book"]')

        for book in books:
            yield{
                "Title": book.xpath('.//div[@class="detail__title"]//a/text()').get(),
                "Author": book.xpath('.//ul[@class="detail__authors"]//a/text()').get(),
                "Date": book.xpath('.//div[@class="detail__date"]//text()').get(),
                "URL": book.xpath('.//div[@class="thumbnail__cover"]/a/@href').get()
            }
        

