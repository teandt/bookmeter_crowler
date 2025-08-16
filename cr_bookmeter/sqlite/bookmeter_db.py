import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String
from sqlalchemy.orm import sessionmaker, relationship
from pathlib import Path

# このスクリプト(bookmeter_db.py)が存在するディレクトリを取得
_basedir = Path(__file__).parent

# DBファイルの絶対パスを構築 (例: /home/tea/code/get-dokusho-meter/cr_bookmeter/sqlite/bookmeter.db)
_db_path = _basedir / "bookmeter.db"

# create_engineに絶対パスを渡すことで、どこから実行しても同じDBファイルを参照するようになります
engine = sqlalchemy.create_engine(f'sqlite:///{_db_path}', echo=True)
Base = declarative_base()

### データベースのテーブル構造の設定 #############################################################################################################
# リストの共通設定
class BookListMixin:
    # book_idは各クラスでリレーション定義と共に個別に定義
    title = Column(String)
    authors = Column(String)
    date = Column(String)
    url = Column(String)

# 読んだ本リスト
class ReadBooks(BookListMixin, Base):
    __tablename__ = 'read_books'
    # 主キーとして定義
    book_id = Column(String, primary_key=True)

    # ORMにリレーションの条件を明示的に教える
    detail = relationship(
        "BookDetail",
        foreign_keys=[book_id],
        primaryjoin="ReadBooks.book_id == BookDetail.book_id",
        back_populates="read_book_entry"
    )

    def __repr__(self):
        return f"<ReadBooks(book_id='{self.book_id}', title='{self.title}', authors='{self.authors}', date='{self.date}', url='{self.url}')>"

# 積読本リスト
class StackedBooks(BookListMixin, Base):
    __tablename__ = 'stacked_books'
    # 主キーとして定義
    book_id = Column(String, primary_key=True)

    # ORMにリレーションの条件を明示的に教える
    detail = relationship(
        "BookDetail",
        foreign_keys=[book_id],
        primaryjoin="StackedBooks.book_id == BookDetail.book_id",
        back_populates="stacked_book_entry"
    )

    def __repr__(self):
        return f"<StackedBooks(book_id='{self.book_id}', title='{self.title}', authors='{self.authors}', date='{self.date}', url='{self.url}')>"

# 書籍詳細
class BookDetail(Base):
    __tablename__ = 'book_detail'
    book_id = Column(String, primary_key=True)
    title = Column(String)
    pages = Column(String)
    amazon_url = Column(String)
    asin = Column(String)

    # ReadBooksとStackedBooksからの逆リレーションを定義
    # uselist=False は、こちら側が「一対一」関係の「一」であることを示す
    read_book_entry = relationship(
        "ReadBooks",
        foreign_keys=[ReadBooks.book_id],
        primaryjoin="BookDetail.book_id == ReadBooks.book_id",
        back_populates="detail",
        uselist=False,
    )
    stacked_book_entry = relationship(
        "StackedBooks",
        foreign_keys=[StackedBooks.book_id],
        primaryjoin="BookDetail.book_id == StackedBooks.book_id",
        back_populates="detail",
        uselist=False,
    )

    def __repr__(self):
        return f"<BookDetail(book_id='{self.book_id}', title='{self.title}', pages='{self.pages}', amazon_url='{self.amazon_url}', asin='{self.asin}')>"

if __name__ == '__main__':
    # テーブルを作成
    Base.metadata.create_all(engine)
