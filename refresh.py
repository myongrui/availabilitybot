import re
import json
import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

CHROME_USER_DATA = os.path.abspath("./chrome_profile_bbdc")

print("Opening browser... Log in to BBDC, then wait.")
print(f"Using dedicated profile at: {CHROME_USER_DATA}")
print("(First run will require login; subsequent runs will remember it.)\n")

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

driver.get("https://booking.bbdc.sg")

print("Waiting for you to log in...")
while True:
    cookies = {c['name']: c['value'] for c in driver.get_cookies()}
    if 'bbdc-token' in cookies:
        print("Logged in! Loading booking page to trigger API calls...")
        break
    time.sleep(2)

driver.get("https://booking.bbdc.sg/#/booking/chooseSlot?courseType=3A")
time.sleep(8)  # give time for API calls to fire

print("Capturing network traffic from /bbdc-back-service/api/...")
logs = driver.get_log("performance")

api_request = None
for entry in logs:
    try:
        msg = json.loads(entry["message"])["message"]
    except Exception:
        continue
    if msg.get("method") != "Network.requestWillBeSent":
        continue
    req = msg["params"].get("request", {})
    url = req.get("url", "")
    if "/bbdc-back-service/api/" in url:
        api_request = req  # keep latest — it carries the freshest cookies

if not api_request:
    print("ERROR: No API request captured. Did the booking page load fully?")
    try:
        driver.quit()
    except Exception:
        pass
    raise SystemExit(1)

req_headers = {k.lower(): v for k, v in api_request["headers"].items()}
cookie_header = req_headers.get("cookie", "")
authorization = req_headers.get("authorization", "")
jsessionid    = req_headers.get("jsessionid", "")

auth_token  = re.sub(r"^Bearer\s+", "", authorization).strip()
jsess_token = re.sub(r"^Bearer\s+", "", jsessionid).strip()

# Fall back to browser cookie store if network log didn't capture Cookie header
if not cookie_header:
    browser_cookies = driver.get_cookies()
    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in browser_cookies)
    print(f"Cookie header not in network log — pulled {len(browser_cookies)} cookies from browser store")

print(f"\nCaptured request: {api_request['url']}")
print(f"  Cookie header length: {len(cookie_header)}")
print(f"  Authorization:        {'set' if auth_token else 'MISSING'}")
print(f"  JSessionId header:    {'set' if jsess_token else 'MISSING'}")

with open('.env', 'r') as f:
    env = f.read()

def update_env(content, key, value):
    if value is None or value == "":
        return content
    pattern = rf'^{key}=.*$'
    replacement = f'{key}={value}'
    if re.search(pattern, content, re.MULTILINE):
        return re.sub(pattern, replacement, content, flags=re.MULTILINE)
    return content + f'\n{key}={value}'

env = update_env(env, 'BBDC_COOKIES',    cookie_header)
env = update_env(env, 'BBDC_TOKEN',      auth_token)
env = update_env(env, 'BBDC_JSESSIONID', jsess_token)

with open('.env', 'w') as f:
    f.write(env)

print("\n.env updated!")
print("  BBDC_COOKIES (raw Cookie header — includes bbdc-token, visid_incap_*, incap_ses_*, etc.)")
print("  BBDC_TOKEN")
print("  BBDC_JSESSIONID")

# --- Test API with captured credentials ---
from dotenv import load_dotenv
load_dotenv()

TOKEN      = os.getenv("BBDC_TOKEN", "")
JSESSIONID = os.getenv("BBDC_JSESSIONID", "")
COOKIES_RAW = os.getenv("BBDC_COOKIES", "")

cookies_dict = dict(
    pair.split("=", 1) for pair in COOKIES_RAW.split("; ") if "=" in pair
) if COOKIES_RAW else {}

print("\n--- Testing API with .env credentials ---")
resp = requests.post(
    "https://booking.bbdc.sg/bbdc-back-service/api/booking/c3practical/listC3PracticalSlotReleased",
    headers={
        "authorization": f"Bearer {TOKEN}",
        "jsessionid":    f"Bearer {JSESSIONID}",
        "content-type":  "application/json",
        "origin":        "https://booking.bbdc.sg",
        "referer":       "https://booking.bbdc.sg/",
        "user-agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    },
    cookies=cookies_dict,
    json={"courseType": "3A", "stageSubDesc": "Practical Lesson", "subVehicleType": None, "subStageSubNo": None},
    timeout=15
)

print(f"Status: {resp.status_code}")
try:
    data = resp.json()
    print(f"success: {data.get('success')}")
    slots = (data.get('data') or {}).get('releasedSlotListGroupByDay')
    print(f"slots:   {slots}")
except Exception:
    print("Not JSON (likely WAF blocked):")
    print(resp.text[:500])

print("\nKeeping browser open for 5 minutes to preserve session state...")
for remaining in range(300, 0, -10):
    print(f"  Closing in {remaining}s...", end="\r")
    time.sleep(10)

print("\nClosing browser.")
try:
    driver.quit()
except Exception:
    pass
