import argparse
import logging
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from cr_bookmeter.spiders.bookmeter_read import BookmeterReadSpider
from cr_bookmeter.spiders.bookmeter_stacked import BookmeterStackedSpider
from twisted.internet.error import ReactorNotRestartable

logging.basicConfig(level=logging.INFO, format='%(asctime)s : %(levelname)s : %(name)s - %(message)s')
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(
                    prog='Bookmeter Crawler',
                    description='読書メーターの未読／既読リスト取得ツール',
                    epilog='Text at the bottom of help')
parser.add_argument('-st', '--stacked', help='積読本リスト取得', action='store_true')
parser.add_argument('-rd', '--read', help='読んだ本リスト取得', action='store_true')
parser.add_argument('-vb', '--verbose', help='書籍詳細の取得', action='store_true')
args = parser.parse_args()

if not any(vars(args).values()):
    parser.error("少なくとも1つのオプション (-st, -rd, -vb) を指定してください。")

# CrawlerProcessは一度だけ初期化し、実行したいスパイダーをすべて追加してから
# 最後に一度だけstart()を呼び出します。
settings = get_project_settings()
process = CrawlerProcess(settings)

crawled_something = False
if args.stacked:
    logger.info("積読本リストの取得をキューに追加します。")
    process.crawl(BookmeterStackedSpider)
    crawled_something = True

if args.read:
    logger.info("読んだ本リストの取得をキューに追加します。")
    process.crawl(BookmeterReadSpider)
    crawled_something = True

# キューにスパイダーが追加されている場合のみ、クローリングを開始します。
if crawled_something:
    try:
        logger.info("クローリング処理を開始します...")
        process.start()
        logger.info("クローリング処理が正常に完了しました。")
    except ReactorNotRestartable:
        logger.error("Reactorは再起動できません。スクリプトの構造を確認してください。")
    except Exception as e:
        logger.error(f"クローリング中に予期せぬエラーが発生しました: {e}", exc_info=True)

# 積読本リスト／読んだ本リストで書籍詳細を取得していない本がある場合に詳細を取得する処理

