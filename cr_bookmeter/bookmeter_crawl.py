import argparse

parser = argparse.ArgumentParser(
                    prog='Bookmeter Crawler',
                    description='読書メーターの未読／既読リスト取得ツール',
                    epilog='Text at the bottom of help')
parser.add_argument('-sd', '--stacked', help='積読本リスト取得', action='store_true')
parser.add_argument('-rd', '--read', help='読んだ本リスト取得', action='store_true')
args = parser.parse_args()

if not any(vars(args).values()):
    parser.error("少なくとも1つのオプション (-st, -rd, -vb) を指定してください。")
