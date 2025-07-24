# db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from Models import Base

# Создание движка
engine = create_engine('sqlite:///bot.db')

# Создание сессии
Session = sessionmaker(bind=engine)

# Создание таблиц
def init_db():
    Base.metadata.create_all(engine)
