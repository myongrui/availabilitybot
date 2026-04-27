# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A bot that monitors the BBDC (Bukit Batok Driving Centre) Singapore booking system for available driving lesson slots and sends Telegram notifications when slots open up.

**Architecture note:** the bot drives a real Chrome browser via Selenium and makes API calls *from inside* the loaded booking page using `fetch()`. This is required because BBDC sits behind Imperva/Incapsula WAF, which binds session cookies (`incap_ses_*`) to the live TLS session that issued them. Calling the API from a separate `requests` process — even with copied cookies — gets blocked with a 403 challenge page. Running the calls inside the browser uses the live, trusted session.

## Setup & Running

**Install dependencies** (no requirements.txt — install manually):
```bash
pip install selenium requests python-dotenv
```

You also need Chrome installed and a matching `chromedriver` on PATH (see https://googlechromelabs.github.io/chrome-for-testing/).

**Environment variables** — create a `.env` file:
```
BOT_TOKEN=<telegram_bot_token>
CHAT_ID=<telegram_chat_id>
```

That's all — no BBDC credentials in `.env`. Login is handled interactively in the Chrome window on first run, and Chrome's persistent profile (`./chrome_profile_bbdc/`) remembers it across restarts.

**Run the bot**:
```bash
python Bot.py
```

On first run, a Chrome window opens at `https://booking.bbdc.sg`. Log in manually. The bot detects login (via the `bbdc-token` cookie) and starts polling automatically. Don't close the Chrome window — closing it kills the bot.

## Architecture

**`Bot.py`** — Main and only runtime entrypoint. Launches Chrome with a persistent profile, waits for login, navigates to the booking page, and runs two threads:
- `startBot()` — polls the BBDC APIs every 60s via `find_booking()`, which uses `driver.execute_async_script(JS_FETCH)` to run `fetch()` calls inside the browser. Sends 3x Telegram alerts when slots are found, then waits 180s. Exits with a Telegram alert if the session is blocked or expires.
- `Checker()` — health monitor, sends an hourly heartbeat Telegram message; sends a "stopped" alert if the main thread dies.

**`refresh.py`** — Legacy. Was used to scrape cookies into `.env` for the old `requests`-based approach. No longer needed since `Bot.py` keeps the browser open and uses the live session. Kept around in case the cookie-extraction approach is needed for debugging.

**`chrome_profile_bbdc/`** — Persistent Chrome user-data directory created on first run. Stores login cookies, browsing history, and Imperva fingerprint state. Gitignored. Deleting it forces a fresh login.

## API Endpoints

Both are polled on every check via in-page `fetch()`. Slots are available if either returns data:

- **`listC3PracticalSlotReleased`** — Returns `data.releasedSlotListGroupByDay` (non-null when slots exist)
  - Payload: `{"courseType":"3A","stageSubDesc":"Practical Lesson","subVehicleType":null,"subStageSubNo":null}`

- **`checkExistsC3PracticalTrainingSlot`** — Returns `data` field (non-null when slots exist)
  - Payload: `{"subStageSubNo":null,"insInstructorId":""}`

Headers used by the in-page `fetch()`:
- `authorization: Bearer <authToken>` — pulled from `localStorage.vuex.user.authToken`
- `jsessionid: Bearer <authToken>` — same value as authorization
- `content-type: application/json`
- Cookies are sent automatically via `credentials: 'include'`

## Key Implementation Details

- **Browser-resident execution**: API calls run via `driver.execute_async_script(JS_FETCH)`. This avoids cookie/TLS-fingerprint issues entirely — the request originates from the live booking page, so Imperva treats it like any other XHR.
- **No cookie management in Python**: there's no `BBDC_TOKEN`/`BBDC_JSESSIONID`/`BBDC_COOKIES` anymore. The browser holds session state.
- **Persistent profile**: `./chrome_profile_bbdc/` survives restarts so you don't have to log in every time. BBDC appears to rate-limit logins from the same account in short windows, so minimize re-logins.
- **Telegram still uses `requests`**: Telegram has no WAF, and we want Telegram alerts to fire even if the browser/page becomes unhealthy.
- **`NO_PROXY`** is set to bypass system/VPN proxies for the Telegram call.
- **Session expiry handling**: if either API returns non-200 or `success:false`, the bot fires a Telegram alert and exits. Restart `Bot.py` and re-login (or wait, since BBDC may temporarily block re-logins).
- `test.py`, `test_api.py`, `tempCodeRunnerFile.py` are scratch files — gitignored.
