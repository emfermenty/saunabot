from datetime import datetime, timedelta

from Services import create_hourly_timeslots
from start_handler import run_bot

def main():
    create_hourly_timeslots()
    print("даты занесены")
    print(datetime.utcnow() + timedelta(hours=5))
    run_bot()

if __name__ == "__main__":
    main()