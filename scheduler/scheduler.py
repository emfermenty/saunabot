# scheduler.py
from sched import scheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, and_, func

from Models import TimeSlot, SlotStatus, User
from dbcontext.db import Session
from scheduler.scheduler_handler import send_reminder_to_user, notify_admin_if_needed, notify_admin_signed_3_times

scheduler = AsyncIOScheduler()
tz = ZoneInfo("Asia/Yekaterinburg")
'''напомимание пользователю'''
async def send_reminders_to_users(application):
    print("[scheduler] send_reminders_to_users START")
    now = datetime.now(tz)
    reminder_start = now + timedelta(hours=2) - timedelta(minutes=1)
    reminder_end = now + timedelta(hours=2) + timedelta(minutes=2)

    print(f"[scheduler] now: {now}, checking window: {reminder_start} - {reminder_end}")

    async with Session() as session:
        result = await session.execute(
            select(TimeSlot)
            .where(
                and_(
                    TimeSlot.slot_datetime.between(reminder_start, reminder_end),
                    TimeSlot.status == SlotStatus.PENDING,
                    TimeSlot.isActive == True
                )
            )
        )
        slots = result.scalars().all()
    print(f"[scheduler] found {len(slots)} slot(s)")

    for slot in slots:
        print(f"[scheduler] notifying user {slot.user_id} about {slot.slot_datetime}")
        await send_reminder_to_user(application, slot.user.telegram_id, slot)

'''уведомление админу'''
async def notify_admin_about_unconfirmed_slots(application):
    tz = ZoneInfo("Asia/Yekaterinburg")
    async with Session() as session:
        now = datetime.now(tz)
        print("[scheduler] notify_admin_about_unconfirmed_slots START")

        check_window_start = now + timedelta(minutes=59)
        check_window_end = now + timedelta(hours=1, minutes=1)

        result = await session.execute(
            select(TimeSlot).where(
                and_(
                    TimeSlot.slot_datetime.between(check_window_start, check_window_end),
                    TimeSlot.status == SlotStatus.PENDING,
                    TimeSlot.isActive == True
                )
            )
        )

        unconfirmed_slots = result.scalars().all()
        print(f"[scheduler] found {len(unconfirmed_slots)} unconfirmed slot(s)")

        for slot in unconfirmed_slots:
            await notify_admin_if_needed(application, slot)
async def deactivate_past_slots(application):
    async with Session() as session:
        now = datetime.now(tz)  # Asia/Yekaterinburg
        print("[scheduler] deactivate_past_slots")

        result = await session.execute(
            select(TimeSlot).where(
                and_(
                    TimeSlot.slot_datetime < now,
                    TimeSlot.isActive == True
                )
            )
        )

        past_slots = result.scalars().all()

        for slot in past_slots:
            slot.isActive = False
            slot.status = SlotStatus.CONFIRMED

        await session.commit()
        print(f"[scheduler] Деактивировано слотов: {len(past_slots)}")

async def check_multiple_bookings(application):
    async with Session() as session:
        now = datetime.now(tz)
        window_start = now - timedelta(minutes=5)

        result = await session.execute(
            select(TimeSlot.user_id, func.count(TimeSlot.id).label("count"))
            .where(
                and_(
                    TimeSlot.created_at >= window_start,
                    TimeSlot.created_at <= now,
                    TimeSlot.status.in_([SlotStatus.PENDING, SlotStatus.CONFIRMED])
                )
            )
            .group_by(TimeSlot.user_id)
            .having(func.count(TimeSlot.id) >= 3)
        )

        results = result.all()
        print(f"Найдено {len(results)} пользователей с 3+ слотами за 5 минут")

        for user_id, count in results:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                phone = user.phone
                await notify_admin_signed_3_times(application, user.telegram_id, count, phone)

async def create_new_workday_slots(application):
    async with Session() as session:
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

        print("[scheduler] создаются новые слоты")
        session.add_all(new_slots)
        await session.commit()

def configure_scheduler(application):
    scheduler.add_job(
        send_reminders_to_users,
        CronTrigger(minute=0, timezone="Asia/Yekaterinburg"),
        kwargs={"application": application})
    scheduler.add_job(
        notify_admin_about_unconfirmed_slots,
        CronTrigger(minute=0, timezone="Asia/Yekaterinburg"),
        kwargs={"application": application}
    )
    scheduler.add_job(
        deactivate_past_slots,
        CronTrigger(minute=0, timezone="Asia/Yekaterinburg"),
        kwargs={"application": application}
    )
    scheduler.add_job(
        check_multiple_bookings,
        IntervalTrigger(minutes=1),
        kwargs={"application": application})
    scheduler.add_job(
        create_new_workday_slots,
        CronTrigger(hour=0, minute=0, timezone="Asia/Yekaterinburg"),
        kwargs={"application": application})

def start_scheduler():
    scheduler.start()
