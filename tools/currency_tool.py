"""Currency conversion with European Central Bank rates via Frankfurter (free, no API key)."""
# -----------------------------------------------------------------------------
# tools/currency_tool.py - converts money between currencies.
# Used by the budget agent (through MCP) to turn e.g. a USD budget into EUR.
# -----------------------------------------------------------------------------

import requests   # simple HTTP client

# Frankfurter's "latest rates" endpoint (publishes the ECB's daily reference rates).
RATES_URL = "https://api.frankfurter.dev/v1/latest"


def convert_currency(amount: float, from_currency: str, to_currency: str = "EUR") -> float:
    """Convert an amount between ISO 4217 currencies. Raises on unknown currencies or network errors."""
    # " usd" -> "USD"
    from_currency = from_currency.upper().strip()
    to_currency = to_currency.upper().strip()

    # Same currency: no web request needed.
    if from_currency == to_currency:
        return round(amount, 2)

    # e.g. GET https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR
    # The answer looks like {"base": "USD", "rates": {"EUR": 0.92}, ...}.
    response = requests.get(
        RATES_URL,
        params={"base": from_currency, "symbols": to_currency},
        timeout=15,           # give up after 15 seconds instead of hanging
    )
    response.raise_for_status()   # raise an error for 4xx/5xx answers (e.g. unknown currency)
    rate = response.json()["rates"][to_currency]

    # Amount times rate, rounded to cents.
    return round(amount * rate, 2)
