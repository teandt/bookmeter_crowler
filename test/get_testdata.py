import argparse
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from dotenv import dotenv_values
import requests
from parsel import Selector

logger = logging.getLogger("get_testdata")

# 設定
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"

# パス定義
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "testdata" / "page"
ENV_FILE = SCRIPT_DIR.parent / "cr_bookmeter" / "env" / ".env"
URL_MAP_FILE = SCRIPT_DIR / "testdata" / "url_map.json"

# URLとローカルファイルの対応マップ
url_map = {}

def register_url_map(url, cache_path):
    try:
        rel_path = cache_path.relative_to(SCRIPT_DIR / "testdata")
        url_map[url] = str(rel_path)
    except Exception as e:
        logger.error(f"URLマップ登録エラー: {e}")

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def load_user_id():
    if not ENV_FILE.exists():
        logger.error(f".envファイルが見つかりません: {ENV_FILE}")
        sys.exit(1)
    
    env = dotenv_values(ENV_FILE)
    user_id = env.get("USER_ID")
    if not user_id:
        logger.error("USER_ID が .env ファイルに定義されていません。")
        sys.exit(1)
    return user_id

def get_page_content(url, delay, force, cache_path, max_retries=3, retry_delay=10):
    """
    指定されたURLのコンテンツを取得する。
    forceがFalseで、cache_pathにファイルが存在する場合はそれを読み込んで返す。
    存在しない、またはforceがTrueの場合はリクエストを送信して保存する。
    """
    register_url_map(url, cache_path)
    
    if not force and cache_path.exists():
        logger.info(f"キャッシュを利用します: {cache_path.name}")
        return cache_path.read_text(encoding="utf-8")

    headers = {"User-Agent": USER_AGENT}
    
    for attempt in range(1, max_retries + 1):
        # 待機時間を設定
        if delay > 0 and attempt == 1:
            time.sleep(delay)
        elif attempt > 1:
            # リトライ時は少し長めに待機
            logger.warning(f"リトライします ({attempt}/{max_retries})... {retry_delay}秒待機")
            time.sleep(retry_delay)
            
        try:
            logger.info(f"データを取得中: {url}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            response.encoding = "utf-8"
            content = response.text
            
            # 保存先ディレクトリの作成
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(content, encoding="utf-8")
            logger.info(f"保存しました: {cache_path.name}")
            return content
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None
            logger.warning(f"HTTPエラーが発生しました (ステータス: {status_code}): {e}")
            # 503 や 429 の場合はリトライ対象
            if status_code in [429, 503, 504]:
                if attempt == max_retries:
                    raise
                continue
            else:
                # その他のエラーはリトライせず即座に失敗とする
                raise
        except Exception as e:
            logger.error(f"接続エラーが発生しました: {e}")
            if attempt == max_retries:
                raise

def crawl_list(list_type, user_id, delay, force, limit_pages=0):
    """
    読んだ本または積読本のリストページを巡回取得する。
    """
    page_num = 1
    base_url = f"https://bookmeter.com/users/{user_id}/books/{list_type}"
    current_url = base_url
    
    while current_url:
        cache_path = OUTPUT_DIR / list_type / f"{list_type}_{page_num}.html"
        
        try:
            content = get_page_content(current_url, delay, force, cache_path)
        except Exception:
            logger.error(f"{list_type} の {page_num} ページの取得に失敗しました。巡回を中断します。")
            break
            
        # ページ制限に達した場合は次ページURLを抽出せず終了
        if limit_pages > 0 and page_num >= limit_pages:
            logger.info(f"{list_type} の取得ページ数が上限（{limit_pages}ページ）に達したため、巡回を終了します。")
            break

        selector = Selector(text=content)
        # 次のページのURLを抽出
        next_page = selector.xpath('//ul[@class="bm-pagination"]//a[@rel="next"]/@href').get()
        if next_page:
            current_url = urljoin("https://bookmeter.com", next_page)
            page_num += 1
            # 無限ループ防止用の安全策
            if page_num > 1000:
                logger.warning("ページ数が1000を超えたため、安全のために停止します。")
                break
        else:
            current_url = None

def extract_book_ids():
    """
    保存されているすべての読んだ本・積読本リストのHTMLから、書籍IDを抽出する。
    """
    book_ids = set()
    if not OUTPUT_DIR.exists():
        return book_ids
        
    for list_type in ["read", "stacked"]:
        list_dir = OUTPUT_DIR / list_type
        if not list_dir.exists():
            continue
        for html_file in list_dir.glob(f"{list_type}_*.html"):
            try:
                content = html_file.read_text(encoding="utf-8")
                selector = Selector(text=content)
                # XPathで書籍詳細のhrefを抽出
                hrefs = selector.xpath('//li[@class="group__book"]//div[@class="book__thumbnail"]/div[@class="thumbnail__cover"]/a/@href').getall()
                for href in hrefs:
                    # href の例: "/books/123456"
                    book_id = href.split('/')[-1]
                    if book_id.isdigit():
                        book_ids.add(book_id)
            except Exception as e:
                logger.error(f"ファイル解析エラー {html_file.name}: {e}")
                
    return sorted(list(book_ids))

def crawl_details(book_ids, delay, force, limit_books=0):
    """
    抽出した書籍IDの詳細ページを巡回取得する。
    """
    if limit_books > 0:
        book_ids = book_ids[:limit_books]
        logger.info(f"書籍詳細の取得数を上限（{limit_books}件）に制限します。")

    total = len(book_ids)
    logger.info(f"書籍詳細データの取得を開始します。対象件数: {total}件")
    
    for i, book_id in enumerate(book_ids, 1):
        url = f"https://bookmeter.com/books/{book_id}"
        cache_path = OUTPUT_DIR / "detail" / f"detail_{book_id}.html"
        
        # キャッシュが存在する場合は即座にスキップ
        if not force and cache_path.exists():
            logger.info(f"[{i}/{total}] キャッシュを利用します: {cache_path.name}")
            continue
            
        logger.info(f"[{i}/{total}] ID: {book_id}")
        try:
            get_page_content(url, delay, force, cache_path)
        except Exception as e:
            # 503エラー等が発生しても終了せず、エラーを記録して次の書籍に進む
            logger.error(f"書籍詳細 (ID: {book_id}) の取得に失敗しました（スキップして継続します）: {e}")

def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(
        description="読書メーターのテストデータ（HTML）を取得・保存するツール"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="キャッシュを無視して強制的にダウンロードし直します。"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="リクエスト間の待機秒数（デフォルト: 3.0秒）"
    )
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=0,
        help="リスト取得の最大ページ数（デフォルト: 0（無制限））"
    )
    parser.add_argument(
        "--limit-books",
        type=int,
        default=0,
        help="取得する書籍詳細ページの最大数（デフォルト: 0（無制限））"
    )
    args = parser.parse_args()
    
    user_id = load_user_id()
    logger.info(f"ターゲットユーザーID: {user_id}")
    
    # 保存先フォルダの作成
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info("=== 1. 読んだ本リストの取得 ===")
    crawl_list("read", user_id, args.delay, args.force, args.limit_pages)
    
    logger.info("=== 2. 積読本リストの取得 ===")
    crawl_list("stacked", user_id, args.delay, args.force, args.limit_pages)
    
    logger.info("=== 3. 書籍IDの抽出 ===")
    book_ids = extract_book_ids()
    logger.info(f"抽出されたユニークな書籍ID: {len(book_ids)}件")
    
    logger.info("=== 4. 書籍詳細ページの取得 ===")
    crawl_details(book_ids, args.delay, args.force, args.limit_books)
    
    logger.info("=== 5. URLマッピングの保存 ===")
    try:
        import json
        with open(URL_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(url_map, f, ensure_ascii=False, indent=2)
        logger.info(f"URLマッピングを保存しました: {URL_MAP_FILE}")
    except Exception as e:
        logger.error(f"URLマッピングの保存に失敗しました: {e}")
        
    logger.info("=== 処理が完了しました ===")

if __name__ == "__main__":
    main()
