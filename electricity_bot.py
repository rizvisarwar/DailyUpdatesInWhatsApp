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
    for key in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "TWILIO_CONTENT_SID", "OPENAI_API_KEY", "TIBBER_TOKEN", "PRICE_ZONE"]:
        if os.getenv(key):
            config[key] = os.getenv(key)

    if os.getenv("RECIPIENTS"):
        config["RECIPIENTS"] = json.loads(os.getenv("RECIPIENTS"))

    if os.getenv("USE_OPENAI"):
        config["USE_OPENAI"] = os.getenv("USE_OPENAI", "").lower() in ("1", "true", "yes")

    return config


def fetch_prices_elprisetjust(zone):
    """Fetch hourly prices from elprisetjustnu.se (free, no auth, Nordpool data)."""
    today = date.today()
    url = (
        f"https://www.elprisetjustnu.se/api/v1/prices/"
        f"{today.year}/{today.month:02d}-{today.day:02d}_{zone}.json"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    seen = set()
    prices = []
    for entry in resp.json():
        hour = datetime.fromisoformat(entry["time_start"]).hour
        if hour in seen:
            continue
        seen.add(hour)
        price_ore = entry["SEK_per_kWh"] * 100  # SEK/kWh → öre/kWh
        prices.append({"hour": hour, "price_ore": price_ore})
    return prices


def fetch_prices_tibber(tibber_token):
    """Fetch prices from Tibber API (requires active Tibber home subscription)."""
    query = """
    {
      viewer {
        homes {
          currentSubscription {
            priceInfo {
              today { startsAt total }
            }
          }
        }
      }
    }
    """
    resp = requests.post(
        "https://api.tibber.com/v1-beta/gql",
        json={"query": query},
        headers={"Authorization": f"Bearer {tibber_token}", "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    homes = resp.json()["data"]["viewer"]["homes"]
    if not homes:
        return None
    subscription = homes[0].get("currentSubscription")
    if not subscription:
        return None
    today_prices = subscription["priceInfo"]["today"]
    if not today_prices:
        return None
    prices = []
    for entry in today_prices:
        hour = datetime.fromisoformat(entry["startsAt"]).hour
        price_ore = entry["total"] * 100
        prices.append({"hour": hour, "price_ore": price_ore})
    return prices


def fetch_prices(tibber_token=None, zone="SE3"):
    """Fetch today's hourly prices, trying elprisetjust.nu first, then Tibber."""
    try:
        print(f"Fetching prices from elprisetjust.nu (zone: {zone})...")
        prices = fetch_prices_elprisetjust(zone)
        print(f"Got {len(prices)} hours from elprisetjust.nu.")
        return prices
    except Exception as e:
        print(f"elprisetjust.nu failed: {e}")

    if tibber_token:
        try:
            print("Trying Tibber API...")
            prices = fetch_prices_tibber(tibber_token)
            if prices:
                print(f"Got {len(prices)} hours from Tibber.")
                return prices
            print("Tibber returned no prices (no active subscription).")
        except Exception as e:
            print(f"Tibber failed: {e}")

    raise RuntimeError("Could not fetch electricity prices from any source.")


def analyze_prices(prices, top_n=3):
    """Return the cheapest and most expensive hours.

    Cheapest hours exclude 23:00–08:00 (night hours).
    Returns (cheapest, most_expensive) — each a list of top_n dicts.
    """
    daytime = [p for p in prices if 8 <= p["hour"] < 23]
    sorted_asc = sorted(daytime, key=lambda x: x["price_ore"])
    cheapest = sorted_asc[:top_n]
    most_expensive = list(reversed(sorted_asc[-top_n:]))
    return cheapest, most_expensive


def format_message(prices, cheapest, most_expensive):
    today = date.today().strftime("%Y-%m-%d")
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


def build_template_variables(prices, cheapest, most_expensive):
    """Build variables dict for the Twilio WhatsApp Content Template."""
    today = date.today().strftime("%Y-%m-%d")
    avg = sum(p["price_ore"] for p in prices) / len(prices)

    def fmt_hours(hours):
        return "\n".join(
            f"{p['hour']:02d}:00–{p['hour']+1:02d}:00  {p['price_ore']:.1f} öre/kWh"
            for p in hours
        )

    return {
        "1": today,
        "2": f"{avg:.1f}",
        "3": fmt_hours(cheapest),
        "4": fmt_hours(most_expensive),
    }


def send_whatsapp(message, recipients, config, content_variables=None):
    client = Client(config["TWILIO_ACCOUNT_SID"], config["TWILIO_AUTH_TOKEN"])
    from_number = config["TWILIO_WHATSAPP_FROM"]
    content_sid = config.get("TWILIO_CONTENT_SID")

    for to in recipients:
        to_number = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to
        if content_sid and content_variables:
            client.messages.create(
                content_sid=content_sid,
                content_variables=json.dumps(content_variables),
                from_=from_number,
                to=to_number,
            )
        else:
            client.messages.create(body=message, from_=from_number, to=to_number)
        print(f"Sent to {to}")


def main():
    config = load_config()
    tibber_token = config.get("TIBBER_TOKEN")
    if not tibber_token:
        raise ValueError("TIBBER_TOKEN is not set. Add it to config.json or as a GitHub secret.")
    recipients = config.get("RECIPIENTS", [])

    zone = config.get("PRICE_ZONE", "SE3")
    prices = fetch_prices(tibber_token, zone)
    cheapest, most_expensive = analyze_prices(prices)
    message = format_message(prices, cheapest, most_expensive)

    if config.get("USE_OPENAI") and config.get("OPENAI_API_KEY"):
        message = refine_with_openai(message, config["OPENAI_API_KEY"])

    print("Message:\n", message)

    content_variables = build_template_variables(prices, cheapest, most_expensive)

    if config.get("TWILIO_ACCOUNT_SID") and config["TWILIO_ACCOUNT_SID"] != "your_account_sid":
        send_whatsapp(message, recipients, config, content_variables)
    else:
        print("\n(Twilio not configured — message printed above, not sent)")


if __name__ == "__main__":
    main()
