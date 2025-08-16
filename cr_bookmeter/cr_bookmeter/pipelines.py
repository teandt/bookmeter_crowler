# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class CrBookmeterPipeline:
    def process_item(self, item, spider):
        # spider.nameでどのスパイダーから渡されたItemかを判別
        if spider.name == 'bookmeter_read':
            # BookmeterReadSpiderの場合の処理
            adapter = ItemAdapter(item)
            spider.logger.info(f"--- [Read Books Pipeline] Received item from [{spider.name}] ---")
            spider.logger.info(adapter.asdict())
            # ここに「読んだ本」用のDB保存処理などを記述します

            return item
        
        elif spider.name == 'bookmeter_stacked':
            # BookmeterStackedSpiderの場合の処理
            adapter = ItemAdapter(item)
            spider.logger.info(f"--- [Stacked Books Pipeline] Received item from [{spider.name}] ---")
            spider.logger.info(f"Processing stacked book: {adapter.get('short_title')}")
            # ここに「積読本」用のDB保存処理などを記述します
            
            return item
        
        # 上記以外のスパイダーの場合は、そのままItemを返します
        return item
