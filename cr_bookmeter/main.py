from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
#from cr_bookmeter.spiders.bookmeter_read import BookmeterReadSpider
from cr_bookmeter.spiders.bookmeter_stacked import BookmeterStackedSpider

settings = get_project_settings()
settings.set('FEED_FORMAT', 'json')
settings.set('FEED_URI', 'output_read2.json')

process = CrawlerProcess(settings)
#process.crawl(BookmeterReadSpider)
process.crawl(BookmeterStackedSpider)
process.start()
