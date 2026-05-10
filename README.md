# BBDC Booking Bot

Monitors the [BBDC](https://booking.bbdc.sg) booking system for available Class 3A practical lesson slots and sends Telegram notifications when they open up.

## Requirements

**Python packages** (no requirements.txt — install manually):
```bash
pip install selenium requests python-dotenv pytesseract Pillow
```

**System dependencies:**
- Chrome + matching `chromedriver` on PATH → https://googlechromelabs.github.io/chrome-for-testing/
- Tesseract OCR at `C:\Program Files\Tesseract-OCR\tesseract.exe` → https://github.com/UB-Mannheim/tesseract/wiki

## Setup

Create a `.env` file in the project root:

```
BOT_TOKEN=<telegram_bot_token>
CHAT_ID=<telegram_chat_id>
BBDC_ID=<bbdc_login_id>
BBDC_PASSWORD=<bbdc_password>
```

## Running

```bash
python Bot.py
```

Chrome opens at `https://booking.bbdc.sg`. The bot auto-logs in, solves the captcha with Tesseract OCR (up to 5 attempts), and navigates to the booking page. Don't close the Chrome window — it kills the bot.

If all 5 captcha attempts fail, the bot sends the captcha image to your Telegram chat and waits up to 2 minutes for you to reply with the answer.

## Telegram Commands

Once running, the bot accepts commands via Telegram:

| Command | Effect |
|---------|--------|
| `/status` | Shows time since last check and whether slots were found |
| `/check` | Forces an immediate slot check |
| `/stop` | Stops the bot process |

A startup message listing these commands is sent when the bot is ready.

## Credentials Refresh

If the bot reports session errors, run:

```bash
python refresh.py
```

Opens Chrome, waits for login, captures fresh auth headers from network traffic, writes them to `.env`, then tests the API.

## Architecture

| File | Purpose |
|------|---------|
| `Bot.py` | Main entrypoint — browser, login, polling loop, Telegram I/O |
| `refresh.py` | Credential capture utility |
| `chrome_profile_bbdc/` | Persistent Chrome profile (gitignored) |

**Two threads run inside `Bot.py`:**
- `startBot()` — polls every 60s. Tries `requests.post()` with captured headers first; falls back to in-browser `fetch()` via `execute_async_script` if WAF blocks.
- `Checker()` — polls Telegram every 5s for commands (`/status`, `/check`, `/stop`); sends an hourly heartbeat; alerts if the main thread dies.

**Header capture** happens on first poll and whenever a WAF block or non-JSON response invalidates the cache. The booking page is only refreshed when the cache is empty — not on every 60s poll.

## WAF Note

BBDC sits behind Imperva/Incapsula WAF. The primary strategy is to replay real browser headers via `requests`. On a WAF block (503/429/HTML response), the cache is invalidated and the call is retried inside the live browser session, which always bypasses the WAF.
