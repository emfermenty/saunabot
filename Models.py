#ЗДЕСЬ МОДЕЛИ ОТРАЖАЮЩИЕ ТАБЛИЦУ БАЗЫ ДАННЫХ
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean, Enum
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy import Enum
from enum import Enum as PyEnum

Base = declarative_base()

class UserRole(PyEnum):
    USER = "пользователь"
    ADMIN = "админ"

class SlotStatus(PyEnum):
    PENDING = "Ожидание"
    CONFIRMED = "Подтверждено"
    CANCELED = "Отменено"

class User(Base):
    __tablename__ = 'users'

    telegram_id = Column(Integer, primary_key=True, unique=True)
    phone = Column(String, nullable=True, unique=True)
    role = Column(Enum(UserRole, name='user_role'), default=UserRole.USER)
    time_slots = relationship("TimeSlot", back_populates="user")
    count_of_sessions = Column(Integer, nullable=True)
    # Связи


class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    price = Column(Integer, nullable=False)

    # Связи
    time_slots = relationship("TimeSlot", back_populates="event")


class TimeSlot(Base):
    __tablename__ = 'time_slots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('users.telegram_id'), nullable=True)
    slot_datetime = Column(DateTime, nullable=False, unique=True)
    isActive = Column(Boolean, default=True)
    comment = Column(String, nullable=True)
    status = Column(Enum(SlotStatus, name="slot_status"), nullable=True)
    created_at = Column(DateTime, nullable=True)
    # Связи
    event = relationship("Event", back_populates="time_slots")
    user = relationship("User", back_populates="time_slots")

class Subscription(Base):
    __tablename__ = 'subscriptios'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=True)
    countofsessions = Column(Integer)

engine = create_engine('sqlite:///bot.db')
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

