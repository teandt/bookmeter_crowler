import argparse
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s : %(levelname)s : %(name)s - %(message)s')
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

logger.info("hogehoge")

# 積読本リストの取得処理


# 読んだ本リストの取得処理


# 積読本リスト／読んだ本リストで書籍詳細を取得していない本がある場合に詳細を取得する処理

