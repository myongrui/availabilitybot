import os
import time
import logging
import requests
import threading
from threading import Timer
import time
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Telegram API endpoint
url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'

# Payload
payload = {
    'chat_id': CHAT_ID,
    'text': "Lesson Available!"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

profile_path = os.getenv("profile_path")
options = Options()
options.set_preference("profile", profile_path)

driver = webdriver.Firefox(options=options)
driver.get("https://booking.bbdc.sg/#/booking/chooseSlot?courseType=3A&insInstructorId=&instructorType=")

time.sleep(60)

def find_booking(driver):

    calendar = driver.find_element(By.CSS_SELECTOR, ".v-calendar-monthly")
    button = None

    try:
        button = calendar.find_element(By.TAG_NAME, "button")
        logging.info("Booking Found")
        return True
    
    except Exception as e:
        pass

    logging.info("No Booking Found")
    return False

def Checker(thread):

    while thread.is_alive():

        payload = {
        'chat_id': CHAT_ID,
        'text': "BOT 🟢"
        }

        response = requests.post(url, data=payload)

        if response.status_code == 200:
            print('Notification sent successfully!')
        else:
            print(f'Failed to send notification: {response.text}')

        time.sleep(3600)


def startBot():

    payload = {
        'chat_id': CHAT_ID,
        'text': "Bot is now online!"
    }

    response = requests.post(url, data=payload)

    while True:

        logging.info("Refreshing page...")
        driver.refresh()
        time.sleep(60)

        found = find_booking(driver)

        if found:
            # Send the message
            response = requests.post(url, data=payload)

            # Check result
            if response.status_code == 200:
                print('Notification sent successfully!')
            else:
                print(f'Failed to send notification: {response.text}')

main = threading.Thread(target = startBot)
tracker = threading.Thread(target = Checker, args=(main,))

main.start()
tracker.start()
