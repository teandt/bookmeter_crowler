from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from cr_bookmeter.spiders.bookmeter import BookmeterSpider

process = CrawlerProcess(get_project_settings())
process.crawl(BookmeterSpider)
process.start()
