#ТОЧКА ВХОДА В ПРОГРАММУ
from datetime import datetime, timedelta, timezone
from start_handler import run_bot

def main():
    #create_hourly_timeslots()
    print("даты занесены")
    print(datetime.now(timezone.utc) + timedelta(hours=5))
    run_bot()

if __name__ == "__main__":
    main()