import requests
from datetime import datetime, date
import json
import os

from twilio.rest import Client

CONFIG_PATH = "config.json"


def load_config(path=CONFIG_PATH):
    config = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)

    # Environment variables override config file (used by GitHub Actions secrets)
    for key in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "OPENAI_API_KEY"]:
        if os.getenv(key):
            config[key] = os.getenv(key)

    if os.getenv("RECIPIENTS"):
        config["RECIPIENTS"] = json.loads(os.getenv("RECIPIENTS"))

    if os.getenv("PRICE_ZONE"):
        config["PRICE_ZONE"] = os.getenv("PRICE_ZONE")

    if os.getenv("USE_OPENAI"):
        config["USE_OPENAI"] = os.getenv("USE_OPENAI", "").lower() in ("1", "true", "yes")

    return config


def fetch_prices(zone="SE3"):
    """Fetch today's hourly spot prices from elprisetjust.nu (free Nordpool data).

    E.ON bases their variable pricing on these Nordpool spot prices.
    Zone: SE1 (north), SE2, SE3 (Stockholm/central), SE4 (south/Malmö).

    Returns a list of dicts: {"hour": int, "price_ore": float}
    """
    today = date.today()
    url = (
        f"https://elprisetjust.nu/api/v1/prices/"
        f"{today.year}/{today.month:02d}-{today.day:02d}_{zone}.json"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    prices = []
    for entry in resp.json():
        hour = datetime.fromisoformat(entry["time_start"]).hour
        price_ore = entry["SEK_per_kWh"] * 100  # Convert SEK/kWh → öre/kWh
        prices.append({"hour": hour, "price_ore": price_ore})

    return prices


def analyze_prices(prices, top_n=3):
    """Return the cheapest and most expensive hours.

    Returns (cheapest, most_expensive) — each a list of top_n dicts.
    """
    sorted_asc = sorted(prices, key=lambda x: x["price_ore"])
    cheapest = sorted_asc[:top_n]
    most_expensive = sorted_asc[-top_n:][::-1]
    return cheapest, most_expensive


def format_message(prices, cheapest, most_expensive):
    today = date.today().strftime("%d/%m/%Y")
    avg = sum(p["price_ore"] for p in prices) / len(prices)

    lines = [
        f"⚡ Elpriser {today}",
        f"Snitt idag: {avg:.1f} öre/kWh",
        "",
        "🟢 Billigaste timmarna:",
    ]
    for p in cheapest:
        h = p["hour"]
        lines.append(f"  {h:02d}:00–{h+1:02d}:00  {p['price_ore']:.1f} öre/kWh")

    lines.append("")
    lines.append("🔴 Dyraste timmarna:")
    for p in most_expensive:
        h = p["hour"]
        lines.append(f"  {h:02d}:00–{h+1:02d}:00  {p['price_ore']:.1f} öre/kWh")

    lines.append("")
    lines.append("Ha en bra dag! 😊")
    return "\n".join(lines)


def refine_with_openai(message, api_key):
    """Optionally rewrite the message with OpenAI (gpt-4o-mini, very cheap ~$0.001/day)."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": (
                "Rewrite this electricity price update as a friendly Swedish WhatsApp message. "
                "Keep it short and include the key information:\n\n" + message
            )
        }],
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


def send_whatsapp(message, recipients, config):
    client = Client(config["TWILIO_ACCOUNT_SID"], config["TWILIO_AUTH_TOKEN"])
    from_number = config["TWILIO_WHATSAPP_FROM"]
    for to in recipients:
        to_number = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to
        client.messages.create(body=message, from_=from_number, to=to_number)
        print(f"Sent to {to}")


def main():
    config = load_config()
    zone = config.get("PRICE_ZONE", "SE3")
    recipients = config.get("RECIPIENTS", [])

    prices = fetch_prices(zone)
    cheapest, most_expensive = analyze_prices(prices)
    message = format_message(prices, cheapest, most_expensive)

    if config.get("USE_OPENAI") and config.get("OPENAI_API_KEY"):
        message = refine_with_openai(message, config["OPENAI_API_KEY"])

    print("Message:\n", message)

    if config.get("TWILIO_ACCOUNT_SID") and config["TWILIO_ACCOUNT_SID"] != "your_account_sid":
        send_whatsapp(message, recipients, config)
    else:
        print("\n(Twilio not configured — message printed above, not sent)")


if __name__ == "__main__":
    main()
