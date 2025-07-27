import asyncio
from datetime import datetime, timedelta, timezone
from Services import create_hourly_timeslots
from start_handler import run_bot

if __name__ == "__main__":
    asyncio.run(create_hourly_timeslots())
    print("даты занесены")
    print(datetime.now(timezone.utc) + timedelta(hours=5))

    run_bot()
