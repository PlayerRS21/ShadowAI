from datetime import datetime
from zoneinfo import ZoneInfo

def cleanAll():
    with open("shadowAI_logs.txt","w") as file:
        txt = r"""_____ _               _                      _____   _
 / ____| |             | |               /\   |_   _| | |
| (___ | |__   __ _  __| | _____      __/  \    | |   | |     ___   __ _ ___
 \___ \| '_ \ / _` |/ _` |/ _ \ \ /\ / / /\ \   | |   | |    / _ \ / _` / __|
 ____) | | | | (_| | (_| | (_) \ V  V / ____ \ _| |_  | |___| (_) | (_| \__ \
|_____/|_| |_|\__,_|\__,_|\___/ \_/\_/_/    \_\_____| |______\___/ \__, |___/
                                                                      __/ |
                                                                     |___/"""
        txt = txt + f"\n\n {datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%A, %d %B %Y, %I:%M %p IST")}\n"
        file.write(txt)

def writeToFile(txt):
    with open("shadowAI_logs.txt","a") as file:
        txt = "\n" + str(txt) + f"------{datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%I:%M %p")}\n"
        file.write(txt)

