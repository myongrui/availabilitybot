import io
import os
import re
import sys
import json
import time
import base64
import logging
import requests
import threading
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

load_dotenv()

os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

BOT_TOKEN     = os.getenv("BOT_TOKEN")
CHAT_ID       = os.getenv("CHAT_ID")
BBDC_USERNAME = os.getenv("BBDC_ID", "")
BBDC_PASSWORD = os.getenv("BBDC_PASSWORD", "")

CHROME_USER_DATA = os.path.abspath("./chrome_profile_bbdc")
TELEGRAM_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
BOOKING_URL = "https://booking.bbdc.sg/#/booking/chooseSlot?courseType=3A"
LIST_API = "https://booking.bbdc.sg/bbdc-back-service/api/booking/c3practical/listC3PracticalSlotReleased"
# CHECK_API = "https://booking.bbdc.sg/bbdc-back-service/api/booking/c3practical/checkExistsC3PracticalTrainingSlot"

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
        const listResp = await fetch('/bbdc-back-service/api/booking/c3practical/listC3PracticalSlotReleased', {
            method: 'POST', headers, credentials: 'include',
            body: JSON.stringify({courseType:"3A", stageSubDesc:"Practical Lesson", subVehicleType:null, subStageSubNo:null})
        }).then(r => r.text().then(t => ({status:r.status, body:t})));
        // const checkResp = await fetch('/bbdc-back-service/api/booking/c3practical/checkExistsC3PracticalTrainingSlot', {
        //     method: 'POST', headers, credentials: 'include',
        //     body: JSON.stringify({subStageSubNo:null, insInstructorId:""})
        // }).then(r => r.text().then(t => ({status:r.status, body:t})));
        callback({list: listResp});
    } catch (e) {
        callback({error: String(e)});
    }
})();
"""


_CAPTCHA_CONFIGS = [
    {'scale': 3, 'threshold': 100, 'psm': 7},
    {'scale': 3, 'threshold': 120, 'psm': 7},
    {'scale': 3, 'threshold': 140, 'psm': 7},
    {'scale': 3, 'threshold': 160, 'psm': 7},
    {'scale': 3, 'threshold': 120, 'psm': 8},
    {'scale': 3, 'threshold': 140, 'psm': 8},
    {'scale': 2, 'threshold': 120, 'psm': 7},
    {'scale': 2, 'threshold': 140, 'psm': 7},
    {'scale': 3, 'threshold': 127, 'psm': 13},
]

def _preprocess(raw, scale, threshold):
    w, h = raw.size
    img = raw.convert('L')
    img = img.resize((w * scale, h * scale), Image.LANCZOS)
    img = img.filter(ImageFilter.MedianFilter(3))
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.point(lambda x: 0 if x < threshold else 255, '1')
    return img

def read_captcha_image(driver):
    """Extract base64 captcha, try multiple Tesseract configs, return most common result."""
    cover_el = driver.find_element(
        By.XPATH,
        "//div[contains(@class,'form-captcha-image')]//div[contains(@class,'v-image__image--cover')]"
    )
    style = cover_el.get_attribute('style')
    match = re.search(r'url\("data:image/png;base64,([^"]+)"\)', style)
    if not match:
        return None

    raw = Image.open(io.BytesIO(base64.b64decode(match.group(1))))

    # Save raw captcha for debugging
    raw.save('captcha_debug.png')

    results = []
    for cfg in _CAPTCHA_CONFIGS:
        try:
            img = _preprocess(raw, cfg['scale'], cfg['threshold'])
            config = f"--psm {cfg['psm']} --oem 1 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            text = ''.join(c for c in pytesseract.image_to_string(img, config=config).strip() if c.isalnum())
        except Exception as e:
            logging.warning(f"  cfg {cfg} failed: {e}")
            continue
        if text:
            results.append(text)
            logging.info(f"  cfg scale={cfg['scale']} thresh={cfg['threshold']} psm={cfg['psm']} → '{text}'")

    if not results:
        return None

    from collections import Counter
    filtered = [r for r in results if 4 <= len(r) <= 8]
    pool = filtered if filtered else results
    best, count = Counter(pool).most_common(1)[0]
    logging.info(f"Captcha consensus: '{best}' ({count}/{len(results)} configs agreed)")
    return best


def auto_login(driver):
    if not BBDC_USERNAME or not BBDC_PASSWORD:
        return
    try:
        # --- Step 1: fill credentials and submit ---
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))

        login_field = driver.find_element(
            By.XPATH,
            "//div[contains(@class,'v-text-field__slot')][.//label[contains(text(),'Login')]]//input"
        )
        password_field = driver.find_element(
            By.XPATH,
            "//div[contains(@class,'v-text-field__slot')][.//label[contains(text(),'Password')]]//input"
        )
        login_field.clear()
        login_field.send_keys(BBDC_USERNAME)
        password_field.clear()
        password_field.send_keys(BBDC_PASSWORD)

        driver.find_element(
            By.XPATH,
            "//button[.//span[contains(text(),'Access to Booking System')]]"
        ).click()
        logging.info("Credentials submitted. Waiting for next page...")

        # --- Step 2: handle optional OTP page ---
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//button[.//span[contains(text(),'Send OTP')]]"))
            )
            logging.info("OTP page detected — clicking Send OTP...")
            driver.find_element(By.XPATH, "//button[.//span[contains(text(),'Send OTP')]]").click()
            time.sleep(2)
        except Exception:
            pass  # no OTP page, continue to captcha

        # --- Step 3: wait for captcha page and solve ---
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Refresh')]"))
        )
        logging.info("Captcha page loaded.")
        time.sleep(1)

        for attempt in range(1, 6):
            captcha_text = read_captcha_image(driver)
            if not captcha_text:
                logging.warning(f"Captcha attempt {attempt}: could not read image, refreshing...")
                driver.find_element(By.XPATH, "//a[contains(text(),'Refresh')]").click()
                time.sleep(1)
                continue

            captcha_field = driver.find_element(
                By.XPATH,
                "//div[contains(@class,'v-text-field__slot')][.//label[contains(text(),'Captcha')]]//input"
            )
            logging.info(f"Captcha attempt {attempt}: read '{captcha_text}'")
            driver.execute_script("arguments[0].value = '';", captcha_field)
            captcha_field.send_keys(Keys.CONTROL + 'a')
            captcha_field.send_keys(Keys.DELETE)
            captcha_field.send_keys(captcha_text)

            driver.find_element(
                By.XPATH,
                "//button[.//span[contains(text(),'Verify')]]"
            ).click()
            time.sleep(2)

            # Still on captcha page if Refresh link is still present
            if driver.find_elements(By.XPATH, "//a[contains(text(),'Refresh')]"):
                logging.warning(f"Captcha attempt {attempt}: wrong answer, retrying...")
                driver.find_element(By.XPATH, "//a[contains(text(),'Refresh')]").click()
                time.sleep(1)
            else:
                logging.info("Captcha solved. Login complete.")
                return

        logging.warning("All captcha attempts failed — please solve manually.")
    except Exception as e:
        logging.warning(f"Auto-login skipped (fill manually): {e}")


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
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.set_script_timeout(30)

    driver.get("https://booking.bbdc.sg")
    time.sleep(3)
    auto_login(driver)
    logging.info("Waiting for login to complete (solve captcha if prompted)...")
    while True:
        cookies = {c['name']: c['value'] for c in driver.get_cookies()}
        if 'bbdc-token' in cookies:
            break
        time.sleep(2)

    logging.info("Logged in. Loading booking page...")
    driver.get(BOOKING_URL)
    logging.info("Waiting for booking page to load...")
    time.sleep(10)
    driver.get_log("performance")  # drain initial network log
    return driver


def capture_headers(driver):
    """Refresh the booking page and extract API headers from network traffic."""
    logging.info("Refreshing booking page to capture headers...")
    driver.refresh()
    time.sleep(8)

    logs = driver.get_log("performance")
    api_request = None
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue

        if msg.get("method") != "Network.requestWillBeSent":
            continue

        req = msg["params"].get("request", {})
        if "bbdc-back-service/api" in req.get("url", ""):
            api_request = req  # keep overwriting to get the last (freshest) request

    if not api_request:
        logging.warning("No BBDC API requests found in network log after refresh")
        return None, None, None

    hdrs = {k.lower(): v for k, v in api_request["headers"].items()}
    auth       = hdrs.get("authorization", "")
    jsess      = hdrs.get("jsessionid", "")
    cookie_str = hdrs.get("cookie", "")

    logging.info(f"Headers captured (auth: {'set' if auth else 'MISSING'}, cookies len: {len(cookie_str)})")
    return auth, jsess, cookie_str


def call_api(auth, jsess, cookie_str, url, payload):
    headers = {
        "authorization": auth,
        "jsessionid":    jsess,
        "content-type":  "application/json",
        "origin":        "https://booking.bbdc.sg",
        "referer":       "https://booking.bbdc.sg/",
        "user-agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    }
    cookies = dict(
        pair.split("=", 1) for pair in cookie_str.split("; ") if "=" in pair
    ) if cookie_str else {}

    session = requests.Session()
    session.trust_env = False
    return session.post(url, headers=headers, cookies=cookies, json=payload, timeout=15)


def find_booking(driver):
    auth, jsess, cookie_str = capture_headers(driver)

    if not auth:
        logging.error("Could not capture headers — falling back to in-browser fetch")
        return find_booking_js(driver)

    try:
        list_resp = call_api(auth, jsess, cookie_str, LIST_API,
                             {"courseType": "3A", "stageSubDesc": "Practical Lesson",
                              "subVehicleType": None, "subStageSubNo": None})
    except Exception as e:
        logging.error(f"requests.post failed: {e}")
        return False

    if list_resp.status_code != 200:
        logging.error(f"HTTP {list_resp.status_code} — list: {list_resp.text[:300]}")
        send_telegram("Session blocked — restart Bot.py and re-login")
        sys.exit(1)

    try:
        list_data = list_resp.json()
    except ValueError:
        logging.error(f"Non-JSON response (WAF?) — list: {list_resp.text[:300]}")
        logging.info("Falling back to in-browser fetch...")
        return find_booking_js(driver)

    if not list_data.get('success'):
        logging.warning(f"API failure — list: {list_data}")
        send_telegram("Session expired — restart Bot.py and re-login")
        sys.exit(1)

    list_slots = list_data.get('data', {}).get('releasedSlotListGroupByDay')
    logging.info(f"list: {list_slots}")

    if list_slots:
        logging.info("Booking Found!")
        return True
    logging.info("No slots available")
    return False


def find_booking_js(driver):
    """Fallback: run the API call inside the browser to bypass WAF."""
    try:
        result = driver.execute_async_script(JS_FETCH)
    except Exception as e:
        logging.error(f"execute_async_script failed: {e}")
        return False

    if result.get('error'):
        logging.error(f"JS fetch error: {result['error']}")
        return False

    list_raw = result.get('list', {})

    if list_raw.get('status') != 200:
        logging.error(f"HTTP {list_raw.get('status')} — list: {list_raw.get('body','')[:300]}")
        send_telegram("Session blocked — restart Bot.py and re-login")
        sys.exit(1)

    try:
        list_data = json.loads(list_raw['body'])
    except ValueError:
        logging.error(f"Non-JSON response — list: {list_raw['body'][:300]}")
        send_telegram("Session blocked (WAF) — restart Bot.py and re-login")
        sys.exit(1)

    if not list_data.get('success'):
        logging.warning(f"API failure — list: {list_data}")
        send_telegram("Session expired — restart Bot.py and re-login")
        sys.exit(1)

    list_slots = list_data.get('data', {}).get('releasedSlotListGroupByDay')
    logging.info(f"list (js): {list_slots}")

    if list_slots:
        logging.info("Booking Found!")
        return True
    logging.info("No slots available")
    return False


def startBot(driver):
    while True:
        logging.info("Checking API...")
        if find_booking(driver):
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
