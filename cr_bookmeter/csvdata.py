# サービスID, アイテムID, 13桁ISBN, カテゴリ, 評価, 読書状況, レビュー, タグ, 読書メモ(非公開), 登録日時, 読了日
class booklog_csv_data:
    def __init__(self, service_id, item_id, isbn, category, rating, read_status, review, tags, private_memo, registered_date, read_date):
        self.service_id = service_id
        self.item_id = item_id
        self.isbn = isbn
        self.category = category
        self.rating = rating
        self.read_status = read_status
        self.review = review
        self.tags = tags
        self.private_memo = private_memo
        self.registered_date = registered_date
        self.read_date = read_date

    def to_list(self):
        return [
            self.service_id,
            self.item_id,
            self.isbn,
            self.category,
            self.rating,
            self.read_status,
            self.review,
            self.tags,
            self.private_memo,
            self.registered_date,
            self.read_date
        ]
