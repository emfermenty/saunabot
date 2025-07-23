#ЭТО НЕ ТРОГАТЬ (планировщик делает дима)
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from Models import TimeSlot, SlotStatus
from db import Session

scheduler = AsyncIOScheduler()

def check_slots_and_nofity_admin():
    session = Session()
    now = datetime.utcnow() + timedelta(hours=5)

    reminder_time = now + timedelta(hours=2)
    slots = session.query(TimeSlot).filter(
        TimeSlot.slot_datetime.between(now + timedelta(minutes=119), reminder_time),
        TimeSlot.status == SlotStatus.PENDING
    ).all()
    for slot in slots:
        send_reminder_to_user(slot.user.telegram_id, slot)  # реализуй сам

        # Шаг 2: если прошло больше 1 часа
    too_late_time = now - timedelta(hours=1)
    unconfirmed_slots = session.query(TimeSlot).filter(
        TimeSlot.slot_datetime <= too_late_time,
        TimeSlot.status == SlotStatus.PENDING,
        TimeSlot.notified == False
    ).all()

    for slot in unconfirmed_slots:
        notify_admin_if_needed(slot.user.phone)  # реализуй сам
        slot.notified = True

    session.commit()
    session.close()


scheduler.add_job(check_slots_and_nofity_admin, "interval", minutes=1)
scheduler.start()
