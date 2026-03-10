# WhatsApp Daily Electricity Price Updates

A bot that sends daily Swedish electricity price summaries to WhatsApp every morning. Built with GitHub Actions (free scheduling), Twilio (WhatsApp delivery), and the elprisetjustnu.se API (free Nordpool price data).

## What it does

Every morning at ~7:00 AM Swedish time, the bot:

1. Fetches today's hourly electricity spot prices for your zone (default: SE3)
2. Identifies the **3 cheapest hours** (daytime only, 08:00–23:00)
3. Identifies the **3 most expensive hours**
4. Sends a formatted WhatsApp message to all configured recipients

Example message:
```
⚡ Elpriser 10/03/2026
Snitt idag: 82.4 öre/kWh

🟢 Billigaste timmarna:
  13:00–14:00  61.2 öre/kWh
  14:00–15:00  63.8 öre/kWh
  12:00–13:00  65.1 öre/kWh

🔴 Dyraste timmarna:
  08:00–09:00  112.3 öre/kWh
  17:00–18:00  108.7 öre/kWh
  18:00–19:00  104.2 öre/kWh

Ha en bra dag! 😊
```

## Price sources

1. **Primary**: [elprisetjustnu.se](https://www.elprisetjustnu.se/) — free REST API, no authentication required, Nordpool data
2. **Fallback**: [Tibber API](https://developer.tibber.com/) — requires an active Tibber electricity subscription

## Setup

### 1. Fork or clone this repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

### 2. Configure Twilio for WhatsApp

1. Sign up at [twilio.com](https://www.twilio.com/)
2. Enable the **WhatsApp Sandbox** (or a production WhatsApp sender)
3. Note your **Account SID**, **Auth Token**, and **WhatsApp From number**
4. Have recipients send the sandbox join message to activate their number

### 3. Add GitHub Secrets

In your repository go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token |
| `TWILIO_WHATSAPP_FROM` | Twilio WhatsApp number, e.g. `whatsapp:+14155238886` |
| `RECIPIENTS` | JSON array of phone numbers, e.g. `["+46701234567", "+46709876543"]` |
| `TIBBER_TOKEN` | Your Tibber API token (used as fallback if primary source fails) |
| `OPENAI_API_KEY` | *(Optional)* OpenAI API key for AI-formatted messages |

### 4. Configure price zone

The default zone is **SE3** (central Sweden / Stockholm region). Swedish zones:

| Zone | Region |
|------|--------|
| SE1  | Norra Sverige (Luleå) |
| SE2  | Norra mellansverige (Sundsvall) |
| SE3  | Södra mellansverige (Stockholm) |
| SE4  | Södra Sverige (Malmö) |

To change zone, update the `PRICE_ZONE` secret or modify `config.json`.

### 5. (Optional) Enable AI formatting

Set `USE_OPENAI: "true"` in the workflow file and add the `OPENAI_API_KEY` secret to use GPT-4o-mini to rewrite messages in a friendlier tone (~$0.001/day).

## Schedule

The workflow runs daily at **05:00 UTC**, which equals:
- 07:00 CEST (summer, UTC+2)
- 06:00 CET (winter, UTC+1)

To adjust, edit the cron expression in [.github/workflows/daily_update.yml](.github/workflows/daily_update.yml).

## Manual trigger

You can trigger the workflow manually from the **Actions** tab in GitHub → select the workflow → click **Run workflow**.

## Local development

```bash
pip install -r requirements.txt
```

Copy the example config and fill in your real credentials:

```bash
cp config.example.json config.json
```

Edit `config.json` with your credentials. **`config.json` is in `.gitignore` — never commit it.**

Run:

```bash
python electricity_bot.py
```

If Twilio is not configured (account SID left as placeholder), the message is printed to the console instead of being sent.

## Files

| File | Description |
|------|-------------|
| `electricity_bot.py` | Main bot script |
| `config.example.json` | Configuration template (safe to commit — no real credentials) |
| `config.json` | Your local config with real credentials — **gitignored, never committed** |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes `config.json` and other sensitive files |
| `.github/workflows/daily_update.yml` | GitHub Actions scheduled workflow |

## Cost

| Service | Cost |
|---------|------|
| GitHub Actions | Free (2,000 minutes/month on free tier) |
| elprisetjustnu.se API | Free |
| Twilio WhatsApp (sandbox) | Free for testing |
| Twilio WhatsApp (production) | ~$0.005 per message |
| OpenAI GPT-4o-mini | ~$0.001/day (optional) |
