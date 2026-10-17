"""Currency conversion with European Central Bank rates via Frankfurter (free, no API key)."""

import requests

RATES_URL = "https://api.frankfurter.dev/v1/latest"


def convert_currency(amount: float, from_currency: str, to_currency: str = "EUR") -> float:
    """Convert an amount between ISO 4217 currencies. Raises on unknown currencies or network errors."""
    from_currency = from_currency.upper().strip()
    to_currency = to_currency.upper().strip()

    if from_currency == to_currency:
        return round(amount, 2)

    response = requests.get(
        RATES_URL,
        params={"base": from_currency, "symbols": to_currency},
        timeout=15,
    )
    response.raise_for_status()
    rate = response.json()["rates"][to_currency]

    return round(amount * rate, 2)
