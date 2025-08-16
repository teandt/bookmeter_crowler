import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker

engine = sqlalchemy.create_engine('sqlite:///bookmeter.db', echo=True)
Base = declarative_base()

# 積読本と読んだ本リストの共通項目
class BookList:
    book_id = Column(String, primary_key=True)
    title = Column(String)
    authors = Column(String)
    date = Column(String)
    url = Column(String)

# 読んだ本リスト
class ReadBooks(BookList, Base):
    __tablename__ = 'read_books'

    def __repr__(self):
        return f"<ReadBooks(book_id='{self.book_id}', title='{self.title}', authors='{self.authors}', date='{self.date}', url='{self.url}')>"

# 積読本リスト
class StackedBooks(BookList, Base):
    __tablename__ = 'stacked_books'

    def __repr__(self):
        return f"<StackedBooks(book_id='{self.book_id}', title='{self.title}', authors='{self.authors}', date='{self.date}', url='{self.url}')>"

if __name__ == '__main__':
    # テーブルを作成
    Base.metadata.create_all(engine)
