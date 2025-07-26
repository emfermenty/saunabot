# services.py
#ФУНКЦИИ ДЛЯ ВЗАИМОДЕЙСТВИЯ С БАЗОЙ ДАННЫХ
#ЗДЕСЬ ФУНКЦИИ КОТОРЫЕ делают некий select/update/delete
from datetime import datetime, timedelta, time, date

from sqlalchemy.orm import joinedload

from Models import User, Event, TimeSlot, SlotStatus, UserRole, Subscription
from dbcontext.db import Session
from sqlalchemy import func, extract, select

async def get_or_create_user(telegram_id: int):
    async with Session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()

        if not user:
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.commit()
            await session.refresh(user)

        return user

async def update_user_phone(telegram_id: int, phone: str):
    async with Session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalars().first()
        if user:
            user.phone = phone
            await session.commit()

async def get_all_events():
    async with Session() as session:
        result = await session.execute(select(Event))
        return result.scalars().all()

'''получение даты'''
async def get_available_dates():
    async with Session() as session:
        now = datetime.now()

        result = await session.execute(
            select(func.date(TimeSlot.slot_datetime))
            .where(
                TimeSlot.slot_datetime >= now,
                TimeSlot.isActive == True
            )
            .distinct()
            .order_by(func.date(TimeSlot.slot_datetime))
        )

        dates = result.all()
        return [datetime.strptime(date[0], "%Y-%m-%d").date() for date in dates]

'''закрывает целый день'''
async def close_session_of_day(selected_date: str):
    async with Session() as session:
        try:
            date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
            start_datetime = datetime.combine(date_obj, datetime.min.time())
            end_datetime = datetime.combine(date_obj + timedelta(days=1), datetime.min.time())

            result = await session.execute(
                select(TimeSlot).where(
                    TimeSlot.slot_datetime >= start_datetime,
                    TimeSlot.slot_datetime < end_datetime,
                    TimeSlot.isActive == True
                ).order_by(TimeSlot.slot_datetime)
            )
            slots = result.scalars().all()

            for slot in slots:
                slot.isActive = False

            await session.commit()

            return [{
                'time': slot.slot_datetime.strftime("%H:%M"),
                'full_datetime': slot.slot_datetime.strftime("%Y-%m-%d %H:%M"),
                'slot_id': slot.id
            } for slot in slots]

        except Exception as e:
            await session.rollback()
            raise e

async def get_user_bookings(telegram_id: int):
    async with Session() as session:
        result = await session.execute(
            select(TimeSlot).where(
                TimeSlot.user_id == telegram_id,
                TimeSlot.isActive == True
            ).order_by(TimeSlot.slot_datetime)
        )
        return result.scalars().all()

'''получение времени в дате + 1 час'''
async def get_available_times_by_date(date_str: str):
    async with Session() as session:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        min_datetime = datetime.now() + timedelta(hours=1)

        result = await session.execute(
            select(TimeSlot).where(
                extract('year', TimeSlot.slot_datetime) == date.year,
                extract('month', TimeSlot.slot_datetime) == date.month,
                extract('day', TimeSlot.slot_datetime) == date.day,
                TimeSlot.user_id == None,
                TimeSlot.isActive == True,
                TimeSlot.slot_datetime >= min_datetime
            ).order_by(TimeSlot.slot_datetime)
        )
        return result.scalars().all()

'''должно запускать только при первом запуске'''
async def create_hourly_timeslots(days: int = 5):
    async with Session() as session:
        today = datetime.now().date()
        new_slots = []
        day_offset = 0
        created_days = 0

        while created_days < days:
            current_date = today + timedelta(days=day_offset)
            if current_date.weekday() < 5:  # Пн–Пт
                for hour in range(9, 22):
                    slot_dt = datetime.combine(current_date, time(hour=hour))
                    new_slots.append(TimeSlot(
                        slot_datetime=slot_dt,
                        user_id=None,
                        event_id=None,
                        isActive=True
                    ))
                created_days += 1
            day_offset += 1

        session.add_all(new_slots)
        await session.commit()


async def confirm_booking_bd(procedure, user_id, slot_id):
    async with Session() as session:
        slot = await session.get(TimeSlot, slot_id)
        if slot:
            slot.user_id = user_id
            slot.event_id = int(procedure) if procedure else None
            slot.status = SlotStatus.PENDING
            slot.created_at = datetime.now()
            await session.commit()

async def confirm_booking_bd_with_sertificate(procedure: int, user_id: int, slot_id: int, event_id: int):
    async with Session() as session:
        try:
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError(f"Пользователь с telegram_id {user_id} не найден.")

            # Списываем занятие
            if procedure == 1:
                if user.count_of_sessions_alife_steam and user.count_of_sessions_alife_steam > 0:
                    user.count_of_sessions_alife_steam -= 1
                else:
                    raise ValueError("Нет оставшихся занятий по сертификату 'Живой пар'.")
            elif procedure == 2:
                if user.count_of_session_sinusoid and user.count_of_session_sinusoid > 0:
                    user.count_of_session_sinusoid -= 1
                else:
                    raise ValueError("Нет оставшихся занятий по сертификату 'Синусоида'.")
            else:
                raise ValueError(f"Неизвестная процедура: {procedure}")

            result = await session.execute(select(TimeSlot).where(TimeSlot.id == slot_id))
            slot = result.scalar_one_or_none()
            if not slot:
                raise ValueError(f"Слот с id {slot_id} не найден.")

            slot.user_id = user_id
            slot.event_id = event_id
            slot.status = SlotStatus.PENDING
            slot.isActive = True
            slot.with_subscribtion = True

            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"Ошибка в confirm_booking_bd_with_sertificate: {e}")
            raise

async def get_event(event_id) -> Event:
    async with Session() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        return result.scalar_one_or_none()

async def get_user_bookings(user_id):
    async with Session() as session:
        result = await session.execute(
            select(
                TimeSlot.id,
                TimeSlot.slot_datetime,
                Event.title,
                TimeSlot.isActive
            )
            .join(Event, TimeSlot.event_id == Event.id)
            .where(TimeSlot.user_id == user_id)
            .where(TimeSlot.isActive == True)
        )
        return result.all()

async def clear_booking(booking_id: int):
    async with Session() as session:
        result = await session.execute(select(TimeSlot).where(TimeSlot.id == booking_id))
        time_slot = result.scalar_one_or_none()
        if time_slot:
            time_slot.user_id = None
            time_slot.event_id = None
            time_slot.isActive = True
            await session.commit()

async def take_phone_by_timeslot(slot: TimeSlot):
    if slot.user_id:
        async with Session() as session:
            result = await session.execute(select(User).where(User.id == slot.user_id))
            user = result.scalar_one_or_none()
            return user.phone if user else None
    return None

async def confirm_timeslot(slot_id: int):
    async with Session() as session:
        result = await session.execute(select(TimeSlot).where(TimeSlot.id == slot_id))
        slot = result.scalar_one_or_none()
        if slot:
            slot.status = SlotStatus.CONFIRMED
            await session.commit()

async def canceled_timeslot(slot_id: int):
    async with Session() as session:
        result = await session.execute(select(TimeSlot).where(TimeSlot.id == slot_id))
        slot = result.scalar_one_or_none()
        if slot:
            slot.status = SlotStatus.CANCELED
            await session.commit()

async def take_only_admins():
    async with Session() as session:
        result = await session.execute(select(User).where(User.role == UserRole.ADMIN))
        return result.scalars().all()

async def load_sertificate() -> list[Subscription]:
    async with Session() as session:
        result = await session.execute(select(Subscription))
        return result.scalars().all()

async def get_sertificate(sertificate_id: int) -> Subscription | None:
    async with Session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == sertificate_id)
        )
        return result.scalar_one_or_none()

async def bind_sertificate_and_user(user_id: int, sertificate_id: int):
    async with Session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()

        sert_result = await session.execute(
            select(Subscription).where(Subscription.id == sertificate_id)
        )
        sert = sert_result.scalar_one_or_none()

        if user and sert:
            user.count_of_sessions_alife_steam = (
                (user.count_of_sessions_alife_steam or 0) + (sert.countofsessions_alife_steam or 0)
            )
            user.count_of_session_sinusoid = (
                (user.count_of_session_sinusoid or 0) + (sert.countofsessions_sinusoid or 0)
            )
            await session.commit()
async def get_unique_slot_dates() -> list[date]:
    async with Session() as session:
        today = date.today()
        result = await session.execute(
            select(func.date(TimeSlot.slot_datetime))
            .where(func.date(TimeSlot.slot_datetime) >= today)
            .distinct()
            .order_by(func.date(TimeSlot.slot_datetime))
        )
        return [row[0] for row in result.all()]


async def get_slots_by_date(date_obj: date) -> list[TimeSlot]:
    async with Session() as session:
        start = datetime.combine(date_obj, datetime.min.time())
        end = datetime.combine(date_obj, datetime.max.time())

        result = await session.execute(
            select(TimeSlot)
            .options(
                joinedload(TimeSlot.user),
                joinedload(TimeSlot.event)
            )
            .where(
                TimeSlot.slot_datetime >= start,
                TimeSlot.slot_datetime <= end,
                TimeSlot.isActive == True
            )
            .order_by(TimeSlot.slot_datetime.asc())
        )
        return result.scalars().all()

'''получение дат где есть незакрытые слоты'''
async def get_available_dates_for_new_slots() -> list[date]:
    async with Session() as session:
        today = datetime.now().date()
        result = await session.execute(
            select(func.date(TimeSlot.slot_datetime))
            .where(
                TimeSlot.slot_datetime >= today,
                TimeSlot.isActive == True,
                TimeSlot.user_id.is_(None)
            )
            .group_by(func.date(TimeSlot.slot_datetime))
        )
        return [datetime.strptime(row[0], "%Y-%m-%d").date() for row in result.all()]

'''получение слотов в целом'''
async def get_slots_to_close_day() -> list[date]:
    async with Session() as session:
        today = datetime.now().date()
        result = await session.execute(
            select(func.date(TimeSlot.slot_datetime))
            .where(TimeSlot.slot_datetime >= today)
            .group_by(func.date(TimeSlot.slot_datetime))
        )
        return [datetime.strptime(row[0], "%Y-%m-%d").date() for row in result.all()]

async def get_free_slots_by_date(date_obj: date) -> list[TimeSlot]:
    async with Session() as session:
        start = datetime.combine(date_obj, datetime.min.time())
        end = datetime.combine(date_obj, datetime.max.time())

        result = await session.execute(
            select(TimeSlot)
            .where(
                TimeSlot.slot_datetime >= start,
                TimeSlot.slot_datetime <= end,
                TimeSlot.isActive == True,
                TimeSlot.user_id.is_(None)
            )
            .order_by(TimeSlot.slot_datetime.asc())
        )
        return result.scalars().all()

async def save_new_slot_comment(slot_id: int, comment: str, event_id: int) -> bool:
    async with Session() as session:
        try:
            result = await session.execute(
                select(TimeSlot).where(TimeSlot.id == slot_id)
            )
            slot = result.scalar_one_or_none()
            if not slot:
                return False

            slot.comment = comment
            slot.event_id = event_id
            slot.status = SlotStatus.CONFIRMED
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] save_new_slot_comment: {e}")
            return False
        
'''удаление с возвратом занятия по сертификату'''
async def close_single_slot(slot_id: int) -> str:
    async with Session() as session:
        try:
            slot_result = await session.get(TimeSlot, slot_id)
            if not slot_result:
                return "Слот не найден."

            slot = slot_result

            if slot.user_id and slot.with_subscribtion:
                user = await session.get(User, slot.user_id)
                if user and slot.event_id:
                    event = await session.get(Event, slot.event_id)

                    if event:
                        if "Синусоида" in event.title and user.count_of_session_sinusoid is not None:
                            user.count_of_session_sinusoid += 1
                        elif "пар" in event.title and user.count_of_sessions_alife_steam is not None:
                            user.count_of_sessions_alife_steam += 1

            # Очищаем слот
            slot.isActive = False
            slot.user_id = None
            slot.event_id = None
            slot.status = None
            slot.with_subscribtion = None

            await session.commit()
            return "Слот успешно закрыт и очищен. Если был занят по сертификату — сессия возвращена."
        finally:
            await session.close()
                      
async def get_all_users():
    async with Session() as session:
        result = await session.execute(select(User).order_by(User.telegram_id))
        users = result.scalars().all()
    return users