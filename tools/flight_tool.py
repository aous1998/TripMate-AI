# -----------------------------------------------------------------------------
# tools/flight_tool.py - live flights from AviationStack (needs AVIATIONSTACK_API_KEY).
#
# The main job is turning human words into airport codes:
#   "from Berlin to Paris"  ->  parse_route()  ->  ("BER", "CDG")
#   then search_flights() asks AviationStack for live flights on that route
#   and format_flight() turns each flight into readable text.
#
# Lookup order for a place name (resolve_location_to_iata):
#   1. already an IATA code?            "CDG"     -> CDG
#   2. hand-picked city table           "berlin"  -> BER
#   3. country -> its main airport      "japan"   -> NRT
#   4. search the full airport database by city/airport name
#
# Note: AviationStack gives live flight STATUS (times, gates, delays), not prices.
# -----------------------------------------------------------------------------
import os 
import re 
# certifi: an up-to-date bundle of trusted HTTPS certificates
import certifi
# airportsdata: offline database of ~7,800 airports (name, city, country, coordinates)
import airportsdata
# pycountry: official list of countries (ISO codes and names)
import pycountry
import requests
from dotenv import load_dotenv

# Load API keys from .env into environment variables.
load_dotenv()

# Tell Python's HTTPS code where the trusted certificates are (avoids SSL errors on some PCs).
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# The AviationStack key (None if missing; search_flights() then returns a helpful message).
API_KEY = os.getenv("AVIATIONSTACK_API_KEY")

# Default origin when user says only destination, e.g. "Japan trip"
# Change this if your default location is not Germany/Frankfurt.
DEFAULT_ORIGIN_IATA = os.getenv("DEFAULT_ORIGIN_IATA", "FRA")


# AviationStack endpoint for live flights.
BASE_URL = "https://api.aviationstack.com/v1/flights"


# Every airport keyed by its 3-letter IATA code, e.g.
# AIRPORTS["BER"] = {"name": "Berlin Brandenburg Airport", "city": "Berlin", "country": "DE", "lat": ..., "lon": ...}
AIRPORTS = airportsdata.load("IATA")



# Nicknames and common names -> 2-letter ISO country code.
# pycountry knows official names ("United Kingdom"); these cover everyday ones ("uk").
COUNTRY_ALIASES = {
    "usa": "US",
    "u.s.a": "US",
    "u.s.": "US",
    "america": "US",
    "united states": "US",
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "england": "GB",
    "uae": "AE",
    "dubai": "AE",
    "south korea": "KR",
    "korea": "KR",
    "russia": "RU",
    "vietnam": "VN",
    "bangladesh": "BD",
    "india": "IN",
    "japan": "JP",
    "china": "CN",
    "singapore": "SG",
    "malaysia": "MY",
    "thailand": "TH",
    "indonesia": "ID",
    "nepal": "NP",
    "qatar": "QA",
    "saudi arabia": "SA",
    "turkey": "TR",
    "canada": "CA",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "italy": "IT",
    "spain": "ES",
}


# Preferred main airport for country-level search
COUNTRY_MAIN_AIRPORT = {
    "BD": "DAC",
    "IN": "DEL",
    "JP": "NRT",
    "US": "JFK",
    "GB": "LHR",
    "AE": "DXB",
    "SG": "SIN",
    "MY": "KUL",
    "TH": "BKK",
    "ID": "CGK",
    "CN": "PEK",
    "KR": "ICN",
    "NP": "KTM",
    "QA": "DOH",
    "SA": "JED",
    "TR": "IST",
    "CA": "YYZ",
    "AU": "SYD",
    "DE": "FRA",
    "FR": "CDG",
    "IT": "FCO",
    "ES": "MAD",
}




# City name -> its main airport. Checked before the big database search,
# because cities often have several airports (London: LHR, LGW, STN ...).
CITY_MAIN_AIRPORT = {
    "berlin": "BER",
    "hamburg": "HAM",
    "munich": "MUC",
    "frankfurt": "FRA",
    "dusseldorf": "DUS",
    "cologne": "CGN",
    "stuttgart": "STR",
    "hannover": "HAJ",
    "nuremberg": "NUE",
    "leipzig": "LEJ",
    "bremen": "BRE",
    "dresden": "DRS",
    "dhaka": "DAC",
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "kolkata": "CCU",
    "chennai": "MAA",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "tokyo": "NRT",
    "osaka": "KIX",
    "kyoto": "KIX",
    "new york": "JFK",
    "london": "LHR",
    "dubai": "DXB",
    "singapore": "SIN",
    "kuala lumpur": "KUL",
    "bangkok": "BKK",
    "doha": "DOH",
    "istanbul": "IST",
    "toronto": "YYZ",
    "sydney": "SYD",
    "paris": "CDG",
    "rome": "FCO",
    "madrid": "MAD",
}


# Simplify a text for matching: lower case, only letters/digits/spaces, and
# without travel words, e.g. "Flights to Japan!" -> "to japan".
def clean_text(text: str) -> str:
    # "  Berlin " -> "berlin"
    text = text.lower().strip()
    # replace every character that is not a-z, 0-9 or whitespace with a space
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # collapse runs of spaces into one
    text = re.sub(r"\s+", " ", text)
    stop_words = [
        "flight", "flights", "ticket", "tickets", "trip", "travel",
        "plan", "complete", "days", "day", "including", "hotel",
        "hotels", "sightseeing", "under", "budget", "info", "information"
    ]
    # keep only the words that are not in stop_words
    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words).strip()



# Turn a country name into its 2-letter ISO code ("germany" -> "DE"), or None.
def country_name_to_code(text: str):
    text = clean_text(text)

    # 1. our alias table
    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]

    # 2. pycountry's lookup (official names and codes, e.g. "Japan", "JP", "JPN")
    try:
        country = pycountry.countries.lookup(text)
        return country.alpha_2
    except LookupError:
        # not found: try the next method
        pass

    # Detect country name inside longer text
    for country in pycountry.countries:
        country_name = country.name.lower()
        if country_name in text:
            return country.alpha_2

    # 3. an alias somewhere inside the text
    for alias, code in COUNTRY_ALIASES.items():
        if alias in text:
            return code

    return None



# Does this airport belong to the given country? The database usually stores
# the 2-letter code, but we also accept the full country name to be safe.
def airport_country_matches(airport: dict, country_code: str) -> bool:
    airport_country = str(airport.get("country", "")).upper().strip()

    if airport_country == country_code:
        return True

    try:
        country = pycountry.countries.get(alpha_2=country_code)
        if country and airport_country.lower() == country.name.lower():
            return True
    except Exception:
        pass

    return False




# The best airport for a whole country (e.g. "Japan" -> "NRT").
# Uses our preferred table first; otherwise scores every airport of that country
# and picks the highest score (international airports win).
def get_best_airport_for_country(country_code: str):
    preferred = COUNTRY_MAIN_AIRPORT.get(country_code)

    if preferred and preferred in AIRPORTS:
        return preferred

    candidates = []

    # Loop over all airports (iata = code, airport = its details).
    for iata, airport in AIRPORTS.items():
        if not iata:
            # skip entries without a code
            continue

        if airport_country_matches(airport, country_code):
            name = str(airport.get("name", "")).lower()
            city = str(airport.get("city", "")).lower()

            score = 0

            if "international" in name:
                score += 50
            if "intl" in name:
                score += 40
            if "capital" in name:
                score += 20
            if city:
                score += 5

            # (score, code) pairs sort by score first
            candidates.append((score, iata))

    if not candidates:
        return None

    # Highest score first; return the code of the winner.
    candidates.sort(reverse=True)
    return candidates[0][1]




def resolve_location_to_iata(location: str):
    """
    Converts country/city/airport/IATA into IATA code.

    Examples:
    Bangladesh -> DAC
    Japan -> NRT
    Dhaka -> DAC
    Tokyo -> NRT
    DAC -> DAC
    """

    # Nothing given -> no code.
    if not location:
        return None

    raw_location = location.strip()

    # Direct IATA code
    # Direct IATA code
    # Exactly three letters, e.g. "cdg" -> check it is a real airport code.
    if re.fullmatch(r"[A-Za-z]{3}", raw_location):
        code = raw_location.upper()
        if code in AIRPORTS:
            return code

    location_clean = clean_text(raw_location)

    if not location_clean:
        return None

    # City preferred airport
    # City preferred airport
    if location_clean in CITY_MAIN_AIRPORT:
        return CITY_MAIN_AIRPORT[location_clean]

    # Country preferred airport
    country_code = country_name_to_code(location_clean)
    if country_code:
        airport = get_best_airport_for_country(country_code)
        if airport:
            return airport

    # Exact city match from airport database
    # Exact city match from airport database
    # Last resort: score every airport by how well its city/name matches.
    city_matches = []

    for iata, airport in AIRPORTS.items():
        city = str(airport.get("city", "")).lower().strip()
        name = str(airport.get("name", "")).lower().strip()

        score = 0

        # exact city name = best match; part of the city name = good match
        if city == location_clean:
            score += 100
        elif location_clean in city:
            score += 70

        # the airport's own name contains the text (e.g. "heathrow")
        if location_clean in name:
            score += 50

        # small bonus for international airports
        if "international" in name:
            score += 10

        if score > 0:
            city_matches.append((score, iata))

    if city_matches:
        city_matches.sort(reverse=True)
        return city_matches[0][1]

    return None




def find_location_mentions(query: str):
    """
    Finds country or city names inside a natural language query.
    """

    # Used by parse_route() when the query has no "from ... to ..." pattern.
    q = query.lower()
    mentions = []

    # Country aliases
    for alias in COUNTRY_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", q):
            mentions.append(alias)

    # Country names from pycountry
    for country in pycountry.countries:
        name = country.name.lower()
        # names shorter than 4 letters are skipped (too many false matches)
        if len(name) >= 4 and re.search(rf"\b{re.escape(name)}\b", q):
            mentions.append(name)

    # City names from our preferred city map
    for city in CITY_MAIN_AIRPORT:
        if re.search(rf"\b{re.escape(city)}\b", q):
            mentions.append(city)

    # Remove duplicate while keeping order
    unique_mentions = []
    for item in mentions:
        if item not in unique_mentions:
            unique_mentions.append(item)

    return unique_mentions


def parse_route(query: str):
    """
    Returns:
    dep_iata, arr_iata

    Can return:
    None, None  -> global live flights
    DAC, NRT    -> filtered route
    DAC, None   -> all flights from DAC
    None, NRT   -> all flights to NRT
    """

    # Try the patterns from most to least specific; the first that matches wins.
    q = query.strip()
    q_lower = q.lower()

    # Global / all-country query
    global_keywords = [
        "all country",
        "all countries",
        "global flight",
        "global flights",
        "all flight",
        "all flights",
        "worldwide flight",
        "worldwide flights",
    ]

    if any(keyword in q_lower for keyword in global_keywords):
        return None, None

    # Direct IATA code route: DAC to NRT
    # Direct IATA code route: DAC to NRT
    # Uses the original text (not lower case) so only CAPITAL 3-letter words count.
    codes = re.findall(r"\b[A-Z]{3}\b", q)

    if len(codes) >= 2:
        dep = codes[0].upper()
        arr = codes[1].upper()
        return dep, arr

    # Pattern: from X to Y
    # Pattern: from X to Y
    # Reading the regex: "from" + (origin, as short as possible) + "to" + (destination),
    # where the destination ends before words like "on/for/under/...", a full stop, or the end.
    match = re.search(
        r"\bfrom\s+(.+?)\s+\bto\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at)\b|[.!?]|$)",
        q_lower,
    )

    if match:
        origin_text = match.group(1)
        dest_text = match.group(2)

        dep_iata = resolve_location_to_iata(origin_text)
        arr_iata = resolve_location_to_iata(dest_text)

        return dep_iata, arr_iata

    # Pattern: to Y from X
    match = re.search(
        r"\bto\s+(.+?)\s+\bfrom\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at)\b|[.!?]|$)",
        q_lower,
    )

    if match:
        dest_text = match.group(1)
        origin_text = match.group(2)

        dep_iata = resolve_location_to_iata(origin_text)
        arr_iata = resolve_location_to_iata(dest_text)

        return dep_iata, arr_iata

    # Pattern: flights from X
    match = re.search(r"\bfrom\s+(.+?)(?:[.!?]|$)", q_lower)

    if match:
        origin_text = match.group(1)
        dep_iata = resolve_location_to_iata(origin_text)
        return dep_iata, None

    # Pattern: flights to X
    match = re.search(r"\bto\s+(.+?)(?:[.!?]|$)", q_lower)

    if match:
        dest_text = match.group(1)
        arr_iata = resolve_location_to_iata(dest_text)
        return None, arr_iata

    # Fallback: find country/city mentions
    mentions = find_location_mentions(q)

    if len(mentions) >= 2:
        dep_iata = resolve_location_to_iata(mentions[0])
        arr_iata = resolve_location_to_iata(mentions[1])
        return dep_iata, arr_iata

    if len(mentions) == 1:
        arr_iata = resolve_location_to_iata(mentions[0])
        return DEFAULT_ORIGIN_IATA, arr_iata

    return None, None


# Turn one AviationStack flight record (a nested dict) into readable text.
# Every value has a fallback ("Unknown", "N/A") because live data is often incomplete.
def format_flight(flight: dict):
    # .get("airline", {}) gives {} if the key is missing, so .get("name") never crashes.
    airline = flight.get("airline", {}).get("name") or "Unknown airline"
    flight_number = flight.get("flight", {}).get("iata") or "Unknown flight number"
    status = flight.get("flight_status") or "Unknown"

    # `or {}` also handles a key that exists but is None.
    dep = flight.get("departure", {}) or {}
    arr = flight.get("arrival", {}) or {}

    dep_airport = dep.get("airport") or "Unknown departure airport"
    dep_iata = dep.get("iata") or "Unknown"
    dep_terminal = dep.get("terminal") or "N/A"
    dep_gate = dep.get("gate") or "N/A"
    dep_scheduled = dep.get("scheduled") or "Unknown"
    dep_delay = dep.get("delay")
    # The delay can be 0 (a real value), so compare with None instead of using `or`.
    dep_delay_text = f"{dep_delay} minutes" if dep_delay is not None else "N/A"

    arr_airport = arr.get("airport") or "Unknown arrival airport"
    arr_iata = arr.get("iata") or "Unknown"
    arr_terminal = arr.get("terminal") or "N/A"
    arr_gate = arr.get("gate") or "N/A"
    arr_scheduled = arr.get("scheduled") or "Unknown"
    arr_delay = arr.get("delay")
    arr_delay_text = f"{arr_delay} minutes" if arr_delay is not None else "N/A"

    # One block of text per flight; .strip() removes the leading/trailing newlines.
    return f"""
Airline: {airline}
Flight: {flight_number}
Status: {status}

Departure:
- Airport: {dep_airport}
- IATA: {dep_iata}
- Terminal: {dep_terminal}
- Gate: {dep_gate}
- Scheduled: {dep_scheduled}
- Delay: {dep_delay_text}

Arrival:
- Airport: {arr_airport}
- IATA: {arr_iata}
- Terminal: {arr_terminal}
- Gate: {arr_gate}
- Scheduled: {arr_scheduled}
- Delay: {arr_delay_text}
""".strip()


# The function the MCP tool "search_flights" calls.
# Returns text in every case (flights, "none found", or an error message), never raises.
def search_flights(query: str, limit: int = 10):
    # Without a key the API cannot be called: explain how to fix it.
    if not API_KEY:
        return (
            "Flight API error: AVIATIONSTACK_API_KEY is missing.\n"
            "Please add this in your .env file:\n"
            "AVIATIONSTACK_API_KEY=your_api_key_here"
        )

    # Words -> airport codes, e.g. ("BER", "CDG"). Either can be None.
    dep_iata, arr_iata = parse_route(query)

    # Query parameters for the API (AviationStack allows at most 100 results).
    params = {
        "access_key": API_KEY,
        "limit": min(limit, 100),
    }

    # Only filter by airport when we found one; None means "any airport".
    if dep_iata:
        params["dep_iata"] = dep_iata

    if arr_iata:
        params["arr_iata"] = arr_iata

    try:
        # e.g. GET https://api.aviationstack.com/v1/flights?access_key=...&dep_iata=BER&arr_iata=CDG
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
        # network problem (no connection, timeout ...)
    except requests.exceptions.RequestException as e:
        return f"Flight API request failed: {e}"
        # the answer was not JSON
    except ValueError:
        return "Flight API returned invalid JSON."

    # AviationStack reports problems (bad key, quota used up ...) as {"error": {...}}.
    if "error" in data:
        error = data["error"]
        return (
            "Flight API error:\n"
            f"Code: {error.get('code', 'Unknown')}\n"
            f"Message: {error.get('message', 'Unknown error')}"
        )

    # The flights are in data["data"] (a list).
    flight_data = data.get("data", [])

    # No flights: say which route we searched, and that prices are not available here.
    if not flight_data:
        route_text = ""

        if dep_iata and arr_iata:
            route_text = f" for route {dep_iata} to {arr_iata}"
        elif dep_iata:
            route_text = f" from {dep_iata}"
        elif arr_iata:
            route_text = f" to {arr_iata}"

        return (
            f"No live flight data found{route_text}.\n\n"
            "Note: AviationStack provides live/status flight data, not ticket prices. "
            "For actual fare prices, use a flight-pricing API such as Amadeus."
        )

    # A heading that says what was searched.
    route_info = "Global live flights"

    if dep_iata and arr_iata:
        route_info = f"Live flights from {dep_iata} to {arr_iata}"
    elif dep_iata:
        route_info = f"Live flights from {dep_iata}"
    elif arr_iata:
        route_info = f"Live flights to {arr_iata}"

    # Format at most `limit` flights and separate them with a Markdown line (---).
    formatted_flights = [format_flight(flight) for flight in flight_data[:limit]]

    return f"{route_info}\n\n" + "\n\n---\n\n".join(formatted_flights)


# Quick manual test: `python tools/flight_tool.py` prints flights for an example query.
if __name__ == "__main__":
    print(search_flights("Plan a 7 days Japan trip from Bangladesh"))
    print("\n" + "=" * 80 + "\n")
    print(search_flights("all country flight info"))