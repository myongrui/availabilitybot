import os
import sys
import time
import logging
import requests
import threading
from threading import Timer
import time
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
#from selenium.webdriver.firefox.options import Options
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# profile_path = os.getenv("profile_path")
# options = Options()
# options.set_preference("profile", profile_path)

# driver = webdriver.Firefox(options=options)
# driver.get("https://booking.bbdc.sg/#/booking/chooseSlot?courseType=3A&insInstructorId=&instructorType=")

# command = "chrome.exe --remote-debugging-port=9222 --user-data-dir=C:/ChromeData"  
# target_directory = r"C:/Program Files/Google/Chrome/Application"
# result = subprocess.Popen(command, cwd=target_directory, shell=True)

options = Options()
options.add_experimental_option("debuggerAddress", "localhost:9222")
driver = webdriver.Chrome(options=options)
driver.get("https://booking.bbdc.sg/#/booking/chooseSlot?courseType=3A&insInstructorId=&instructorType=")

def find_booking(driver):

    try:
        calendar = driver.find_element(By.CSS_SELECTOR, ".v-calendar-monthly")
        button = calendar.find_element(By.TAG_NAME, "button")
        logging.info("Booking Found")
        return True
    
    except Exception as e:
        pass

    try:
        loginfield = driver.find_element(By.CLASS_NAME, "v-text-field__slot")

        logging.info("Back at Login Page...")
        payload = {
        'chat_id': CHAT_ID,
        'text': "Stuck at Login Page"
        }
        response = requests.post(url, data=payload)

        sys.exit(0)

        return False
    
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
    

    payload = {
        'chat_id': CHAT_ID,
        'text': "Bot stopped working... 😢"  
        }
    
    response = requests.post(url, data=payload)

def startBot():

    while True:

        logging.info("Refreshing page...")
        driver.refresh()
        time.sleep(60)
        found = find_booking(driver)

        if found:
            
            payload = {
                'chat_id': CHAT_ID,
                'text': "Lesson Available!"
            }

            response = requests.post(url, data=payload)
            response = requests.post(url, data=payload)
            response = requests.post(url, data=payload)

            if response.status_code == 200:
                print('Notification sent successfully!')
            else:
                print(f'Failed to send notification: {response.text}')

            time.sleep(180)

main = threading.Thread(target = startBot)
tracker = threading.Thread(target = Checker, args=(main,))

main.start()
tracker.start()
