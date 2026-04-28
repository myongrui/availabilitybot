# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A bot that monitors the BBDC (Bukit Batok Driving Centre) Singapore booking system for available driving lesson slots and sends Telegram notifications when slots open up.

**WAF note:** BBDC sits behind Imperva/Incapsula WAF. The primary API strategy is to capture real request headers (auth token + cookies) from the browser's network traffic after page load and replay them via `requests.post()` with `trust_env=False`. If that gets WAF-blocked (non-JSON response), the bot falls back to running the fetch inside the live browser via `execute_async_script`. The in-browser fallback always works since the request originates from the live page session.

## Setup & Running

**Install dependencies** (no requirements.txt — install manually):
```bash
pip install selenium requests python-dotenv pytesseract Pillow
```

You also need:
- Chrome installed and a matching `chromedriver` on PATH (https://googlechromelabs.github.io/chrome-for-testing/)
- Tesseract OCR installed at `C:\Program Files\Tesseract-OCR\tesseract.exe` (https://github.com/UB-Mannheim/tesseract/wiki)

**Environment variables** — create a `.env` file:
```
BOT_TOKEN=<telegram_bot_token>
CHAT_ID=<telegram_chat_id>
BBDC_ID=<bbdc_login_id>
BBDC_PASSWORD=<bbdc_password>
BBDC_TOKEN=<captured_jwt>
BBDC_JSESSIONID=<captured_jwt>
BBDC_COOKIES=<captured_cookie_header>
```

`BBDC_TOKEN`, `BBDC_JSESSIONID`, and `BBDC_COOKIES` are populated by running `refresh.py`. `BBDC_ID` and `BBDC_PASSWORD` enable auto-login.

**Run the bot**:
```bash
python Bot.py
```

On first run, Chrome opens at `https://booking.bbdc.sg`. If not already logged in, the bot auto-fills `BBDC_ID` and `BBDC_PASSWORD`, solves the captcha with Tesseract OCR (up to 5 attempts), and handles the optional OTP page. Don't close the Chrome window — closing it kills the bot.

**Refresh credentials** (run periodically or when the bot reports session errors):
```bash
python refresh.py
```

Opens Chrome, waits for login, navigates to the booking page, captures auth headers from network traffic, writes them to `.env`, tests the API, then keeps the browser open for 5 minutes.

**Test the API directly**:
```bash
python test_api.py
```

Reads credentials from `.env` and fires one API call. Useful for verifying credentials are valid without running the full bot.

## Architecture

**`Bot.py`** — Main runtime entrypoint. Launches Chrome with a persistent profile, auto-logs in, navigates to the booking page, and runs two threads:
- `startBot()` — polls every 60s via `find_booking()`. Tries `capture_headers()` + `call_api()` (requests-based) first; falls back to `find_booking_js()` (in-browser fetch) if WAF blocks. Sends Telegram alerts when slots are found, then waits 180s.
- `Checker()` — health monitor, sends an hourly heartbeat Telegram message; sends a "stopped" alert if the main thread dies.

**`refresh.py`** — Captures fresh credentials from the browser's network traffic and writes them to `.env`. Also tests the API with the captured credentials. Run this when the bot reports session errors or to pre-populate `.env` for `test_api.py`.

**`test_api.py`** — Standalone API test. Reads `BBDC_TOKEN`, `BBDC_JSESSIONID`, `BBDC_COOKIES` from `.env` and fires a single API call. Use this to verify credentials are valid.

**`chrome_profile_bbdc/`** — Persistent Chrome user-data directory. Stores login cookies, browsing history, and Imperva fingerprint state. Gitignored. Deleting it forces a fresh login.

## Login Flow

`Bot.py` handles login automatically:
1. Navigates to `https://booking.bbdc.sg`
2. Detects login page (waits for `input[type='password']`)
3. Fills Login ID (`BBDC_ID`) and Password (`BBDC_PASSWORD`) via Vuetify field selectors
4. Clicks "Access to Booking System"
5. Detects optional OTP page — clicks "Send OTP" if present (5s timeout)
6. Waits up to 30s for captcha page to load
7. Extracts captcha image from `form-captcha-image` CSS background-image (base64 PNG)
8. Runs 9 Tesseract configs (varying scale/threshold/psm) and uses consensus result
9. Up to 5 attempts — refreshes captcha and retries on wrong answer
10. Once logged in (`bbdc-token` cookie present), navigates to booking page

## API Endpoints

Only `listC3PracticalSlotReleased` is active. `checkExistsC3PracticalTrainingSlot` is commented out.

- **`listC3PracticalSlotReleased`** — Returns `data.releasedSlotListGroupByDay` (non-null when slots exist)
  - Payload: `{"courseType":"3A","stageSubDesc":"Practical Lesson","subVehicleType":null,"subStageSubNo":null}`

Headers used:
- `authorization: Bearer <authToken>`
- `jsessionid: Bearer <authToken>`
- `content-type: application/json`
- `origin: https://booking.bbdc.sg`
- `referer: https://booking.bbdc.sg/`
- `user-agent: Chrome/147`
- Cookies from browser store

## Key Implementation Details

- **Dual API strategy**: `find_booking()` tries `requests.post()` with headers captured from network traffic. On non-JSON (WAF block), falls back to `find_booking_js()` which runs `fetch()` inside the browser via `execute_async_script`. The JS fallback always bypasses WAF since it runs in the live page session.
- **Network header capture**: `capture_headers()` refreshes the booking page, waits 8s for API calls to fire, reads CDP performance logs, and returns the last captured BBDC API request's headers (last = freshest cookies).
- **`trust_env=False`**: All `requests` calls to BBDC use a Session with `trust_env=False` to bypass system proxy settings that would route to `127.0.0.1`.
- **Tesseract captcha solver**: 9 preprocessing configs (scale 2x/3x, threshold 100–160, psm 7/8/13) all run; consensus vote wins. Results of length 4–8 chars are preferred. Each config is wrapped in try/except so one bad call can't abort the login.
- **Persistent profile**: `./chrome_profile_bbdc/` survives restarts. BBDC rate-limits re-logins, so minimize deleting this folder.
- **Session expiry handling**: Non-200 HTTP or `success:false` from the API triggers a Telegram alert and `sys.exit(1)`. Restart `Bot.py` and re-run `refresh.py` to recover.
- `test.py`, `tempCodeRunnerFile.py` are scratch files — gitignored. `test_api.py` is a kept utility.
