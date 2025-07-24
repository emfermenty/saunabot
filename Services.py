# services.py
#ФУНКЦИИ ДЛЯ ВЗАИМОДЕЙСТВИЯ С БАЗОЙ ДАННЫХ
#ЗДЕСЬ ФУНКЦИИ КОТОРЫЕ делают некий select/update/delete
from datetime import datetime, timedelta, time
from Models import User, Event, TimeSlot, SlotStatus, UserRole, Subscription
from dbcontext.db import Session
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

'''получение даты'''
def get_available_dates():
    session = Session()
    now = datetime.now()

    unique_dates = session.query(
        func.date(TimeSlot.slot_datetime)
    ).filter(
        TimeSlot.slot_datetime >= now,
        TimeSlot.isActive == True
    ).distinct().order_by(
        func.date(TimeSlot.slot_datetime)
    ).all()

    session.close()

    # Преобразуем строку 'YYYY-MM-DD' в datetime.date
    return [datetime.strptime(date[0], "%Y-%m-%d").date() for date in unique_dates]

'''закрывает целый день'''
def close_session_of_day(selected_date):
    session = Session()
    try:
        # Преобразуем дату в datetime для фильтрации
        date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
        start_datetime = datetime.combine(date_obj, datetime.min.time())
        end_datetime = datetime.combine(date_obj + timedelta(days=1), datetime.min.time())

        # Получаем слоты для выбранной даты
        slots = session.query(TimeSlot).filter(
            TimeSlot.slot_datetime >= start_datetime,
            TimeSlot.slot_datetime < end_datetime,
            TimeSlot.isActive == True
        ).order_by(TimeSlot.slot_datetime).all()

        # Деактивируем слоты
        for slot in slots:
            slot.isActive = False

        session.commit()  # фиксируем изменения

        # Готовим список для отображения
        times = []
        for slot in slots:
            times.append({
                'time': slot.slot_datetime.strftime("%H:%M"),
                'full_datetime': slot.slot_datetime.strftime("%Y-%m-%d %H:%M"),
                'slot_id': slot.id
            })

        return times
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

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

'''получение времени в дате + 3 часа'''
def get_available_times_by_date(date_str: str):
    session = Session()
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    min_datetime = datetime.now() + timedelta(hours=1)

    slots = session.query(TimeSlot).filter(
        extract('year', TimeSlot.slot_datetime) == date.year,
        extract('month', TimeSlot.slot_datetime) == date.month,
        extract('day', TimeSlot.slot_datetime) == date.day,
        TimeSlot.user_id == None,
        TimeSlot.isActive == True,
        TimeSlot.slot_datetime >= min_datetime
    ).order_by(TimeSlot.slot_datetime).all()

    session.close()
    return slots

'''должно запускать только при первом запуске'''
def create_hourly_timeslots(days: int = 5):
    session = Session()
    today = datetime.now().date()

    new_slots = []
    day_offset = 0
    created_days = 0

    while created_days < days:
        current_date = today + timedelta(days=day_offset)
        weekday = current_date.weekday()  # Пн = 0, ..., Вс = 6

        if weekday < 5:  # Только понедельник-пятница
            for hour in range(9, 22):  # Слоты с 9:00 до 21:00
                slot_dt = datetime.combine(current_date, time(hour=hour))
                slot = TimeSlot(
                    slot_datetime=slot_dt,
                    user_id=None,
                    event_id=None,
                    isActive=True
                )
                new_slots.append(slot)
            created_days += 1  # Учитываем только будние дни

        day_offset += 1  # Переход к следующей дате

    session.add_all(new_slots)
    session.commit()
    session.close()


def confirm_booking_bd(procedure, user_id, slot_id):
    session = Session()
    slot = session.query(TimeSlot).get(slot_id)
    slot.user_id = user_id
    slot.event_id = int(procedure) if procedure else None
    slot.status = SlotStatus.PENDING
    slot.created_at = datetime.now()
    session.commit()
    session.close()

def confirm_booking_bd_with_sertificate(procedure: int, user_id: int, slot_id: int, event_id: int):
    session = Session()
    try:
        # Получаем пользователя
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            raise ValueError(f"Пользователь с telegram_id {user_id} не найден.")

        # Списываем занятие по сертификату
        if procedure == 1:  # Живой пар
            if user.count_of_sessions_alife_steam and user.count_of_sessions_alife_steam > 0:
                user.count_of_sessions_alife_steam -= 1
            else:
                raise ValueError("Нет оставшихся занятий по сертификату 'Живой пар'.")
        elif procedure == 2:  # Синусоида
            if user.count_of_session_sinusoid and user.count_of_session_sinusoid > 0:
                user.count_of_session_sinusoid -= 1
            else:
                raise ValueError("Нет оставшихся занятий по сертификату 'Синусоида'.")
        else:
            raise ValueError(f"Неизвестная процедура: {procedure}")

        # Обновляем слот
        slot = session.query(TimeSlot).filter_by(id=slot_id).first()
        if not slot:
            raise ValueError(f"Слот с id {slot_id} не найден.")

        slot.user_id = user_id
        slot.event_id = event_id
        slot.status = SlotStatus.PENDING
        slot.isActive = True
        slot.with_subscribtion = True
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Ошибка в confirm_booking_bd_with_sertificate: {e}")
        raise
    finally:
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

def clear_booking(booking_id):
    session = Session()
    time_slot = session.query(TimeSlot).filter_by(id=booking_id).first()
    if time_slot:
        time_slot.user_id = None
        time_slot.event_id = None
        time_slot.isActive = True
        session.commit()

    session.close()

def take_phone_by_timeslot(slot: TimeSlot):
    if slot.user:
        return slot.user.phone
    return None

def confirm_timeslot(slotid : int):
    session = Session()
    slot = session.query(TimeSlot).filter(TimeSlot.id == slotid).first()
    slot.status = SlotStatus.CONFIRMED
    session.commit()
    session.close()

def canceled_timeslot(slotid : int):
    session = Session()
    slot = session.query(TimeSlot).filter(TimeSlot.id == slotid).first()
    slot.status = SlotStatus.CANCELED
    session.commit()
    session.close()

def take_only_admins():
    session = Session()
    admins = session.query(User).filter(User.role == UserRole.ADMIN).all()
    session.close()
    return admins

def load_sertificate() -> Subscription:
    session = Session()
    sertificate = session.query(Subscription).all()
    session.close()
    return sertificate

def get_sertificate(sertificateId):
    session = Session()
    sertificate = session.query(Subscription).filter(Subscription.id == sertificateId).first()
    session.close()
    return sertificate

def bind_sertificate_and_user(userId : int, sertificate_id : int):
    session = Session()
    user = session.query(User).filter_by(telegram_id=userId).first()
    sert = session.query(Subscription).filter_by(id=sertificate_id).first()
    if user.count_of_sessions_alife_steam:
        user.count_of_sessions_alife_steam += sert.countofsessions_alife_steam
    else:
        user.count_of_sessions_alife_steam = sert.countofsessions_alife_steam
    if user.count_of_session_sinusoid:
        user.count_of_session_sinusoid += sert.countofsessions_sinusoid
    else:
        user.count_of_session_sinusoid = sert.countofsessions_sinusoid
    session.commit()
    session.close()