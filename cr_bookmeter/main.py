from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from cr_bookmeter.spiders.bookmeter import BookmeterSpider

settings = get_project_settings()
settings.set('FEED_FORMAT', 'json')
settings.set('FEED_URI', 'output_read2.json')

process = CrawlerProcess(settings)
process.crawl(BookmeterSpider)
process.start()
