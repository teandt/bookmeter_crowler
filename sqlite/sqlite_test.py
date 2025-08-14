import sqlite3

dbname = 'test.db'

def create_table():
    conn = sqlite3.connect(dbname)
    c = conn.cursor()

    # テーブルの作成
    c.execute(
        'CREATE TABLE persons(id INTEGER PRIMARY KEY AUTOINCREMENT, name STRING)'
    )

    conn.commit()
    conn.close()

def insert_data():
    conn = sqlite3.connect(dbname)
    c = conn.cursor()

    c.execute('INSERT INTO persons(name) values("Taro")')

    conn.commit()
    c.close()
    conn.close()

def select_data():
    conn = sqlite3.connect(dbname)
    c = conn.cursor()

    c.execute('SELECT * FROM persons')
    data = c.fetchall()
    print(data)

    c.close()
    conn.close()


if __name__ == '__main__':
    #create_table()
    #insert_data()
    select_data()
    

