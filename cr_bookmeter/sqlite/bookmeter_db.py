import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker

engine = sqlalchemy.create_engine('sqlite:///bookmeter.db', echo=True)
Base = declarative_base()

class ReadBooks(Base):
    __tablename__ = 'read_books'
    book_id = Column(String, primary_key=True)
    title = Column(String)
    authors = Column(String)
    date = Column(String)
    url = Column(String)

    def __repr__(self):
        return f"<ReadBooks(book_id='{self.book_id}', title='{self.title}', authors='{self.authors}', date='{self.date}', url='{self.url}')>"

