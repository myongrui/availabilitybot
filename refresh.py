import time
import re
import json
import os
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

try:
    driver.quit()
except Exception:
    pass

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
