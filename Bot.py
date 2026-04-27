import os
import sys
import time
import logging
import requests
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv

load_dotenv()

os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHROME_USER_DATA = os.path.abspath("./chrome_profile_bbdc")
TELEGRAM_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
BOOKING_URL = "https://booking.bbdc.sg/#/booking/chooseSlot?courseType=3A"

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
NO_PROXY = {"http": None, "https": None}

JS_FETCH = """
const callback = arguments[arguments.length - 1];
(async () => {
    try {
        const vuex = JSON.parse(localStorage.getItem('vuex') || '{}');
        const authToken = (vuex.user && vuex.user.authToken) || '';
        const headers = {
            'authorization': 'Bearer ' + authToken,
            'jsessionid':    'Bearer ' + authToken,
            'content-type':  'application/json',
        };
        const [listResp, checkResp] = await Promise.all([
            fetch('/bbdc-back-service/api/booking/c3practical/listC3PracticalSlotReleased', {
                method: 'POST', headers, credentials: 'include',
                body: JSON.stringify({courseType:"3A", stageSubDesc:"Practical Lesson", subVehicleType:null, subStageSubNo:null})
            }).then(r => r.text().then(t => ({status:r.status, body:t}))),
            fetch('/bbdc-back-service/api/booking/c3practical/checkExistsC3PracticalTrainingSlot', {
                method: 'POST', headers, credentials: 'include',
                body: JSON.stringify({subStageSubNo:null, insInstructorId:""})
            }).then(r => r.text().then(t => ({status:r.status, body:t}))),
        ]);
        callback({list: listResp, check: checkResp});
    } catch (e) {
        callback({error: String(e)});
    }
})();
"""


def send_telegram(text):
    try:
        requests.post(TELEGRAM_URL, data={'chat_id': CHAT_ID, 'text': text}, proxies=NO_PROXY, timeout=10)
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")


def init_browser():
    logging.info(f"Launching Chrome with profile {CHROME_USER_DATA}")
    options = Options()
    options.add_argument(f"--user-data-dir={CHROME_USER_DATA}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.set_script_timeout(30)

    driver.get("https://booking.bbdc.sg")
    logging.info("Waiting for login (manually log in if needed)...")
    while True:
        cookies = {c['name']: c['value'] for c in driver.get_cookies()}
        if 'bbdc-token' in cookies:
            break
        time.sleep(2)

    logging.info("Logged in. Loading booking page...")
    driver.get(BOOKING_URL)
    time.sleep(5)
    return driver


def find_booking(driver):
    try:
        result = driver.execute_async_script(JS_FETCH)
    except Exception as e:
        logging.error(f"execute_async_script failed: {e}")
        return False

    if result.get('error'):
        logging.error(f"JS fetch error: {result['error']}")
        return False

    import json as _json
    list_raw  = result.get('list',  {})
    check_raw = result.get('check', {})

    if list_raw.get('status') != 200 or check_raw.get('status') != 200:
        logging.error(f"HTTP {list_raw.get('status')}/{check_raw.get('status')} — list: {list_raw.get('body','')[:300]} | check: {check_raw.get('body','')[:300]}")
        send_telegram("Session blocked — restart Bot.py and re-login")
        sys.exit(1)

    try:
        list_data  = _json.loads(list_raw['body'])
        check_data = _json.loads(check_raw['body'])
    except ValueError:
        logging.error(f"Non-JSON response — list: {list_raw['body'][:300]} | check: {check_raw['body'][:300]}")
        send_telegram("Session blocked (WAF) — restart Bot.py and re-login")
        sys.exit(1)

    if not list_data.get('success') or not check_data.get('success'):
        logging.warning(f"API failure — list: {list_data}, check: {check_data}")
        send_telegram("Session expired — restart Bot.py and re-login")
        sys.exit(1)

    list_slots  = list_data.get('data', {}).get('releasedSlotListGroupByDay')
    check_slots = check_data.get('data')
    logging.info(f"list: {list_slots} | check: {check_slots}")

    if list_slots or check_slots:
        logging.info("Booking Found!")
        return True
    logging.info("No slots available")
    return False


def startBot(driver):
    while True:
        logging.info("Checking API...")
        if find_booking(driver):
            send_telegram("Lesson Available!")
            send_telegram("Lesson Available!")
            send_telegram("Lesson Available!")
            time.sleep(180)
        else:
            time.sleep(60)


def Checker(thread):
    while thread.is_alive():
        send_telegram("BOT 🟢")
        time.sleep(3600)
    send_telegram("Bot stopped working... 😢")


driver = init_browser()
main = threading.Thread(target=startBot, args=(driver,), daemon=True)
tracker = threading.Thread(target=Checker, args=(main,), daemon=True)

main.start()
tracker.start()
main.join()
