# services.py
#ФУНКЦИИ ДЛЯ ВЗАИМОДЕЙСТВИЯ С БАЗОЙ ДАННЫХ
#ЗДЕСЬ ФУНКЦИИ КОТОРЫЕ делают некий select/update/delete
from datetime import datetime, timedelta, time, date
from zoneinfo import ZoneInfo

from sqlalchemy.orm import joinedload, selectinload

from Models import User, Event, TimeSlot, SlotStatus, UserRole, Subscription
from dbcontext.db import Session
from sqlalchemy import func, extract, select, case, update

tz = ZoneInfo("Asia/Yekaterinburg")
from sqlalchemy import func, extract, select

async def get_or_create_user(telegram_id: int):
    async with Session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()

        if not user:
            user = User(telegram_id=telegram_id)
            user.count_of_session_sinusoid = 0
            user.count_of_sessions_alife_steam = 0
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

async def get_subscriptions_by_event(event_id: int):
    async with Session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.event_id == event_id)
        )
        return result.scalars().all()
'''получение даты'''
async def get_available_dates():
    async with Session() as session:
        now = datetime.now(tz)

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
        min_datetime = datetime.now(tz) + timedelta(hours=1)

        result = await session.execute(
            select(TimeSlot).where(
                extract('year', TimeSlot.slot_datetime) == date.year,
                extract('month', TimeSlot.slot_datetime) == date.month,
                extract('day', TimeSlot.slot_datetime) == date.day,
                TimeSlot.user_id == None,
                TimeSlot.isActive == True,
                TimeSlot.comment == None,
                TimeSlot.slot_datetime.is_not(None),  # Важно: исключаем NULL!
                TimeSlot.slot_datetime >= min_datetime  # Теперь здесь не будет ошибки
            ).order_by(TimeSlot.slot_datetime)
        )
        return result.scalars().all()
'''должно запускать только при первом запуске'''
async def create_hourly_timeslots(days: int = 5):
    async with Session() as session:
        today = datetime.now(tz).date()
        new_slots = []
        day_offset = 0
        created_days = 0

        while created_days < days:
            current_date = today + timedelta(days=day_offset)
            if current_date.weekday() < 5:  # Пн–Пт
                for hour in range(9, 20):
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
            slot.created_at = datetime.now(tz)
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
async def get_slot_by_id(slot_id: int):
    async with Session() as session:
        result = await session.execute(
            select(TimeSlot)
            .options(
                selectinload(TimeSlot.event),
                selectinload(TimeSlot.user)
            )
            .where(TimeSlot.id == slot_id)
        )
        return result.scalar_one_or_none()
async def clear_booking(booking_id: int):
    async with Session() as session:
        result = await session.execute(select(TimeSlot).where(TimeSlot.id == booking_id))
        time_slot = result.scalar_one_or_none()
        if time_slot:
            time_slot.user_id = None
            time_slot.event_id = None
            time_slot.isActive = True
            time_slot.status = None
            time_slot.created_at = None
            time_slot.with_subscribtion = None
            time_slot.tea = False
            time_slot.towel = False
            time_slot.water = False
            time_slot.sinusoid = False
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
        if not slot:
            print(f"[confirm_timeslot] Слот не найден: id={slot_id}")
            return
        slot.status = SlotStatus.CONFIRMED
        await session.commit()
        print(f"[confirm_timeslot] Слот {slot_id} подтверждён")

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

async def load_sertificate(event_id: int = None):
    async with Session() as session:
        query = select(Subscription)
        if event_id:
            query = query.where(Subscription.event_id == event_id)
        result = await session.execute(query)
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
        today = datetime.now(tz).date()
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
        today = datetime.now(tz).date()
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
            slot.created_at = None

            await session.commit()
            return "Слот успешно закрыт и очищен. Если был занят по сертификату — сессия возвращена."
        finally:
            await session.close()
                      
async def get_all_users():
    async with Session() as session:
        result = await session.execute(select(User).order_by(User.telegram_id))
        users = result.scalars().all()
    return users

async def add_new_booking_day():
    async with Session() as session:
        # Находим максимальную дату слотов в базе
        last_slot = await session.execute(
            select(TimeSlot).order_by(TimeSlot.slot_datetime.desc()).limit(1)
        )
        last_slot = last_slot.scalars().first()

        if last_slot:
            new_date = last_slot.slot_datetime.date() + timedelta(days=1)
        else:
            new_date = datetime.now(tz).date()
        while new_date.weekday() >= 5:
            new_date += timedelta(days=1)
        new_slots = []
        for hour in range(9, 20):
            slot_dt = datetime.combine(new_date, time(hour=hour))
            existing_slot = await session.execute(
                select(TimeSlot).where(TimeSlot.slot_datetime == slot_dt)
            )
            if existing_slot.scalars().first():
                continue
            new_slots.append(TimeSlot(
                slot_datetime=slot_dt,
                user_id=None,
                event_id=None,
                isActive=True,
                status=None,
                comment=None,
                created_at=None,
                with_subscribtion=False
            ))

        if not new_slots:
            return None, new_date

        session.add_all(new_slots)
        await session.commit()
        return True, new_date

'''async def get_unclosed_days():
    now = datetime.now(tz)
    today_date = now.date()
    async with Session() as session:
        subq = (
            select(
                func.date(TimeSlot.slot_datetime).label("slot_date"),
                func.count().label("total_count"),
                func.sum(case((TimeSlot.isActive == False, 1), else_=0)).label("active_count")
            )
            .where(func.date(TimeSlot.slot_datetime) >= today_date)
            .group_by(func.date(TimeSlot.slot_datetime))
            .subquery()
        )

        result = await session.execute(
            select(subq.c.slot_date)
            .where(subq.c.active_count == 0)
        )
        closed_dates = result.scalars().all()

    return closed_dates'''

async def get_unclosed_days():
    now = datetime.now(tz)
    today_date = now.date()

    async with Session() as session:
        result = await session.execute(
            select(func.date(TimeSlot.slot_datetime).label("slot_date"))
            .where(
                func.date(TimeSlot.slot_datetime) >= today_date,
                TimeSlot.isActive == True
            )
            .group_by(func.date(TimeSlot.slot_datetime))
        )

        unclosed_dates = result.scalars().all()

    return unclosed_dates

async def get_closed_days():
    now = datetime.now(tz)
    today_date = now.date()
    async with Session() as session:
        subq = (
            select(
                func.date(TimeSlot.slot_datetime).label("slot_date"),
                func.count().label("total_count"),
                func.sum(case((TimeSlot.isActive == True, 1), else_=0)).label("active_count")
            )
            .where(func.date(TimeSlot.slot_datetime) >= today_date)
            .group_by(func.date(TimeSlot.slot_datetime))
            .subquery()
        )

        result = await session.execute(
            select(subq.c.slot_date)
            .where(subq.c.active_count == 0)
        )
        closed_dates = result.scalars().all()

    return closed_dates

async def open_day_for_booking_by_date(target_date: date) -> bool:

    async with Session() as session:
        # Проверим, есть ли вообще слоты на эту дату
        result = await session.execute(
            select(TimeSlot).where(func.date(TimeSlot.slot_datetime) == target_date)
        )
        slots = result.scalars().all()
        if not slots:
            return False

        # Обновляем слоты
        await session.execute(
            update(TimeSlot)
            .where(func.date(TimeSlot.slot_datetime) == target_date)
            .values(isActive=True)
        )
        await session.commit()
        return True
async def make_admin(telegram_id: int):
    async with Session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.role = UserRole.ADMIN
            await session.commit()
async def make_user(telegram_id: int):
    async with Session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.role = UserRole.USER
            await session.commit()
async def update_cert_counts(telegram_id: int, sinusoid: int, alife_steam: int):
    async with Session() as session:
        # Получаем пользователя через сессию
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()

        if user:
            user.count_of_session_sinusoid = sinusoid
            user.count_of_sessions_alife_steam = alife_steam
            await session.commit()
async def apply_latest_subscription_to_user(telegram_id: int) -> tuple[bool, str]:
    async with Session() as session:
        # Получаем пользователя
        result_user = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result_user.scalar_one_or_none()
        if not user:
            return False, "❌ Пользователь не найден."
        # Получаем последний сертификат
        result_sub = await session.execute(
            select(Subscription).order_by(Subscription.id.desc()).limit(1)
        )
        subscription = result_sub.scalar_one_or_none()
        if not subscription:
            return False, "❌ Сертификаты не найдены."
        # Прибавляем значения
        user.count_of_sessions_alife_steam = (user.count_of_sessions_alife_steam or 0) + (subscription.countofsessions_alife_steam or 0)
        user.count_of_session_sinusoid = (user.count_of_session_sinusoid or 0) + (subscription.countofsessions_sinusoid or 0)
        await session.commit()
        return True, "✅ Сертификат успешно выдан."
async def add_cert_to_user(telegram_id: int, cert_type: str) -> str:
    async with Session() as session:
        user = await session.get(User, telegram_id)
        if not user:
            return "❌ Пользователь не найден."

        if cert_type == "sinusoid":
            user.count_of_session_sinusoid = (user.count_of_session_sinusoid or 0) + 5
            field_text = "Синусоида"
        elif cert_type == "steam":
            user.count_of_sessions_alife_steam = (user.count_of_sessions_alife_steam or 0) + 5
            field_text = "Живой пар"
        else:
            return "❌ Неизвестный тип сертификата."

        await session.commit()
        return f"✅ Добавлено 5 занятий по: {field_text}"

async def clear_single_slot(slot_id: int) -> str:
    async with Session() as session:
        try:
            slot_result = await session.get(TimeSlot, slot_id)
            if not slot_result:
                return "Слот не найден."

            slot = slot_result
            result = slot.user_id
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
            slot.isActive = True
            slot.user_id = None
            slot.event_id = None
            slot.status = None
            slot.with_subscribtion = None
            slot.created_at = None

            await session.commit()
            return result
        finally:
            await session.close()

async def update_timeslot_with_extras(slot_id: int, extras: set[str]):
    async with Session() as session:
        result = await session.execute(select(TimeSlot).where(TimeSlot.id == slot_id))
        slot = result.scalar_one_or_none()
        if slot:
            slot.tea = "tea" in extras
            slot.towel = "towel" in extras
            slot.water = "water" in extras
            slot.sinusoid = "sinusoid" in extras
            await session.commit()

async def get_telegram_user_full_name_and_username(bot, telegram_id: int):
    try:
        chat = await bot.get_chat(chat_id=telegram_id)
        full_name = chat.first_name or ""
        if chat.last_name:
            full_name += " " + chat.last_name
        username = chat.username or "нет"
        return full_name.strip(), username
    except Exception as e:
        print(f"Ошибка при получении данных пользователя {telegram_id}: {e}")
        return "Неизвестный пользователь", "нет"