# scheduler.py
from sched import scheduler

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import DateTime

from Models import TimeSlot, SlotStatus, User
from db import Session
from scheduler_handler import send_reminder_to_user, notify_admin_if_needed, notify_admin_signed_3_times

scheduler = AsyncIOScheduler()

async def send_reminders_to_users(application):
    session = Session()
    reminder_time = DateTime.now + timedelta(hours=2)

    slots = session.query(TimeSlot).filter(
        TimeSlot.slot_datetime.between(DateTime.now + timedelta(minutes=119), reminder_time),
        TimeSlot.status == SlotStatus.PENDING
    ).all()
    for slot in slots:
        await send_reminder_to_user(application, slot.user.telegram_id, slot)
    session.close()

async def notify_admin_about_unconfirmed_slots(application):
    session = Session()
    too_late_time = DateTime.now - timedelta(hours=1)

    unconfirmed_slots = session.query(TimeSlot).filter(
        TimeSlot.slot_datetime <= too_late_time,
        TimeSlot.status == SlotStatus.PENDING,
        TimeSlot.isActive == True
    ).all()

    for slot in unconfirmed_slots:
        await notify_admin_if_needed(application, slot)
    session = Session()
async def deactivate_past_slots(application):
    session = Session()
    now = datetime.utcnow() + timedelta(hours=5)  # Asia/Yekaterinburg
    past_slots = session.query(TimeSlot).filter(
        TimeSlot.slot_datetime < now,
        TimeSlot.isActive == True
    ).all()

    for slot in past_slots:
        slot.isActive = False
        slot.status = SlotStatus.CONFIRMED
    print(f"Деактивировано слотов: {len(past_slots)}")
    session.commit()
    session.close()

async def check_multiple_bookings(application):
    session = Session()
    now = datetime.now()
    window_start = now - timedelta(minutes=5)
    from sqlalchemy import func

    results = session.query(
        TimeSlot.user_id,
        func.count(TimeSlot.id).label("count")
    ).filter(
        TimeSlot.created_at >= window_start,
        TimeSlot.created_at <= now,
        TimeSlot.status.in_([SlotStatus.PENDING, SlotStatus.CONFIRMED])
    ).group_by(TimeSlot.user_id).having(func.count(TimeSlot.id) >= 3).all()
    print(f"Найдено {len(results)} пользователей с 3+ слотами за 5 минут")
    print("работает")
    for user_id, count in results:
        print("а вот тут")
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if user:
            phone = user.phone
            print("а еще тут")
            await notify_admin_signed_3_times(application, user.telegram_id, count, phone)
    session.close()

def create_new_workday_slots(application):
    session = Session()
    tz = ZoneInfo("Asia/Yekaterinburg")
    now = datetime.now(tz).date()

    next_day = now + timedelta(days=6)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)

    new_slots = []
    for hour in range(9, 22):
        slot_dt = datetime.combine(next_day, time(hour=hour)).replace(tzinfo=tz)
        slot = TimeSlot(
            slot_datetime=slot_dt,
            user_id=None,
            event_id=None,
            isActive=True,
            status=None
        )
        new_slots.append(slot)
    print("создались")
    session.add_all(new_slots)
    session.commit()
    session.close()

def configure_scheduler(application):
    # Используй объект scheduler, а не тип
    scheduler.add_job(send_reminders_to_users, IntervalTrigger(hours=1), kwargs={"application": application})
    scheduler.add_job(notify_admin_about_unconfirmed_slots, IntervalTrigger(hours=1), kwargs={"application": application})
    scheduler.add_job(deactivate_past_slots, IntervalTrigger(hours=1), kwargs={"application": application})
    scheduler.add_job(check_multiple_bookings, IntervalTrigger(minutes=1), kwargs={"application": application})
    scheduler.add_job(create_new_workday_slots, CronTrigger(hour=0, minute=0, timezone="Asia/Yekaterinburg"), kwargs={"application": application})

def start_scheduler():
    scheduler.start()
