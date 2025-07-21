# services.py
from datetime import datetime, timedelta, time
from Models import User, Event, TimeSlot
from db import Session
from sqlalchemy import func, extract


def get_or_create_user(telegram_id):
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.commit()
    session.close()
    return user


def update_user_phone(telegram_id, phone):
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if user:
        user.phone = phone
        session.commit()
    session.close()


def get_all_events():
    session = Session()
    events = session.query(Event).all()
    session.close()
    return events


def get_available_dates():
    session = Session()
    now = datetime.now()
    dates = (
        session.query(TimeSlot.slot_datetime)
        .filter(TimeSlot.slot_datetime >= now, TimeSlot.isActive == True)
        .all()
    )
    session.close()
    # Получаем только даты (без времени), сортируем
    unique_dates = sorted({dt[0].date() for dt in dates})
    return unique_dates

def get_user_bookings(telegram_id):
    session = Session()
    bookings = (
        session.query(TimeSlot)
        .filter(TimeSlot.user_id == telegram_id, TimeSlot.isActive == True)
        .order_by(TimeSlot.slot_datetime)
        .all()
    )
    session.close()
    return bookings

def get_available_times_by_date(date_str: str):
    session = Session()
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    slots = session.query(TimeSlot).filter(
        extract('year', TimeSlot.slot_datetime) == date.year,
        extract('month', TimeSlot.slot_datetime) == date.month,
        extract('day', TimeSlot.slot_datetime) == date.day,
        TimeSlot.user_id == None,
        TimeSlot.isActive == True
    ).order_by(TimeSlot.slot_datetime).all()

    session.close()
    return slots

def create_hourly_timeslots(days: int = 30):
    session = Session()
    today = datetime.now().date()

    new_slots = []

    for day_offset in range(days):
        current_date = today + timedelta(days=day_offset)
        for hour in range(9, 22):  # 22 не включается, последний слот в 21:00
            slot_dt = datetime.combine(current_date, time(hour=hour))
            slot = TimeSlot(
                slot_datetime=slot_dt,
                user_id=None,
                event_id=None,
                isActive=True
            )
            new_slots.append(slot)

    session.add_all(new_slots)
    session.commit()
    session.close()

def get_timeslots_by_date(date_str: str):
    session = Session()
    date = datetime.strptime(date_str, "%Y-%m-%d").date()
    slots = session.query(TimeSlot).filter(
        extract('year', TimeSlot.slot_datetime) == date.year,
        extract('month', TimeSlot.slot_datetime) == date.month,
        extract('day', TimeSlot.slot_datetime) == date.day,
        TimeSlot.user_id == None,
        TimeSlot.isActive == True
    ).order_by(TimeSlot.slot_datetime).all()
    session.close()
    return slots

def confirm_booking_bd(procedure, user_id, slot_id):
    session = Session()
    slot = session.query(TimeSlot).get(slot_id)
    slot.user_id = user_id
    slot.event_id = int(procedure) if procedure else None
    session.commit()
    session.close()

def get_event(event_id) -> Event:
    session = Session()
    event = session.query(Event).filter_by(id=event_id).first()
    session.close()
    return event

def get_user_bookings(user_id):
    session = Session()
    bookings = (
        session.query(
            TimeSlot.id,
            TimeSlot.slot_datetime,
            Event.title,
            TimeSlot.isActive
        )
        .join(Event, TimeSlot.event_id == Event.id)
        .filter(TimeSlot.user_id == user_id)
        .all()
    )
    session.close()
    return bookings


def update_booking_status():
    session = Session()
    now = datetime.now()

    slots = session.query(TimeSlot).filter(TimeSlot.status == 'active').all()
    for slot in slots:
        slot_datetime = datetime.combine(slot.date, slot.time)
        if slot_datetime < now:
            slot.status = 'finished'

    session.commit()
    session.close()