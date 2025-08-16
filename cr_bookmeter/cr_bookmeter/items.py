# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy

# 一覧用の項目
class CrBookmeterItem(scrapy.Item):
    id = scrapy.Field()
    short_title = scrapy.Field()
    authors = scrapy.Field()
    date = scrapy.Field()
    url = scrapy.Field()
    amazon_url = scrapy.Field()
    asin = scrapy.Field()

# 詳細用の項目
class CrBookmeterDetailItem(scrapy.Item):
    id = scrapy.Field()
    title = scrapy.Field()
    pages = scrapy.Field()
    amazon_url = scrapy.Field()
    asin = scrapy.Field()
