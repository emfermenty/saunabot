#ТОЧКА ВХОДА В ПРОГРАММУ
from datetime import datetime, timedelta
from start_handler import run_bot

def main():
    #create_hourly_timeslots()
    print("даты занесены")
    print(datetime.utcnow() + timedelta(hours=5))
    run_bot()

if __name__ == "__main__":
    main()