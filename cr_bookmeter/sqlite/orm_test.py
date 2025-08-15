import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker

engine = sqlalchemy.create_engine('sqlite:///test2.db', echo=True)
Base = declarative_base()

class Book(Base):
    __tablename__ = 'books'
    book_id = Column(Integer, primary_key=True)
    title = Column(String)
    author = Column(String)
    url = Column(String)
    amazon_url = Column(String)
    asin = Column(String)

    def __repr__(self):
        return "<Book(title='%s', author='%s')>" % (self.title, self.author)

class ReadBook(Base):
    __tablename__ = 'read_books'
    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer)
    date = Column(String)

    def __repr__(self):
        return "<ReadBook(book_id='%s', date='%s')>" % (self.book_id, self.date)

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

if __name__ == '__main__':
    # Create
    book = Book(title='test', author='test', url='test', amazon_url='test', asin='test')
    session.add(book)
    session.commit()

    # Read
    for book in session.query(Book).all():
        print(book)

    # Update
    book = session.query(Book).filter_by(title='test').first()
    book.title = 'test2'
    session.commit()

    # Delete
    book = session.query(Book).filter_by(title='test2').first()
    session.delete(book)
    session.commit()
