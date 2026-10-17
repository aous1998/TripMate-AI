"""Input and output guardrails.

Input:  rule-based checks run before any LLM call (length, prompt injection,
        card numbers). Off-topic requests are caught by the supervisor's
        structured output (SupervisorDecision.is_travel_request).
Output: secrets are redacted and the budget check is computed in code, so
        the final answer never relies on the LLM's arithmetic.
"""

import re

from langchain_core.messages import AIMessage

from state import TravelState


MAX_INPUT_CHARS = 1500

INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|your|all)\b.{0,20}\b(instructions?|prompts?|rules)\b",
    r"\b(reveal|show|print|repeat|leak)\b.{0,30}\b(system|hidden|initial)\s+(prompt|instructions?)",
    r"\bsystem\s+prompt\b",
    r"\b(jailbreak|DAN mode|developer mode)\b",
    r"\bact as\b.{0,20}\b(unfiltered|unrestricted|uncensored)\b",
]

SECRET_PATTERNS = [
    r"\bgsk_[A-Za-z0-9]{20,}",                    # Groq
    r"\btvly-[A-Za-z0-9-]{20,}",                  # Tavily
    r"\bsk-[A-Za-z0-9_-]{20,}",                   # OpenAI-style keys
    r"(postgres(?:ql)?://[^:\s/]+:)[^@\s]+(@)",   # database password in a URL
]

BLOCK_MESSAGES = {
    "empty": "Please describe the trip you'd like to plan.",
    "too_long": f"That request is too long. Please keep it under {MAX_INPUT_CHARS} characters.",
    "prompt_injection": (
        "I can only help with planning travel, so I can't follow instructions to change "
        "how I work. Tell me where you'd like to go and I'll plan the trip."
    ),
    "card_number": (
        "It looks like your message contains a payment card number. Please remove it: "
        "TripMate never needs card details to plan a trip."
    ),
    "off_topic": (
        "I'm a travel planner, so I can only help with trips: flights, hotels, weather, "
        "local tips, itineraries and budgets. Where would you like to go?"
    ),
}


def check_input(text: str) -> str | None:
    """Return the reason the input is blocked, or None if it may proceed."""
    text = (text or "").strip()

    if not text:
        return "empty"
    if len(text) > MAX_INPUT_CHARS:
        return "too_long"
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in INJECTION_PATTERNS):
        return "prompt_injection"
    if contains_card_number(text):
        return "card_number"

    return None


def contains_card_number(text: str) -> bool:
    for match in re.finditer(r"\b(?:\d[ -]?){13,19}\b", text):
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            return True
    return False


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace anything that looks like an API key or DB password. Returns (text, count)."""
    count = 0
    for pattern in SECRET_PATTERNS:
        def replace(match):
            # Keep the URL around a database password, drop only the password.
            if match.lastindex == 2:
                return f"{match.group(1)}[redacted]{match.group(2)}"
            return "[redacted]"

        text, n = re.subn(pattern, replace, text)
        count += n
    return text, count


def budget_check_note(budget: dict | None) -> str:
    """A budget verdict computed from the itemised estimate, not written by the LLM."""
    if not budget or budget.get("error") or budget.get("budget_eur") is None:
        return ""

    total = budget["total_eur"]
    limit = budget["budget_eur"]

    if budget["within_budget"]:
        return f"✅ **Budget check:** the estimated total of €{total:,.0f} is within your budget of €{limit:,.0f}."
    return (
        f"⚠️ **Budget check:** the estimated total of €{total:,.0f} is €{total - limit:,.0f} "
        f"over your budget of €{limit:,.0f}. Consider fewer nights, a cheaper hotel or nearby dates."
    )


# =========================
# Graph nodes
# =========================

def input_guardrail(state: TravelState):
    reason = check_input(state["user_query"])
    if reason:
        return {"guardrail": {"blocked": True, "reason": reason}}
    return {"guardrail": {"blocked": False, "reason": ""}}


def route_after_input(state: TravelState) -> str:
    return "blocked_response" if state["guardrail"]["blocked"] else "supervisor"


def blocked_response(state: TravelState):
    message = BLOCK_MESSAGES[state["guardrail"]["reason"]]
    return {
        "final_answer": message,
        "guardrail_notes": [f"Request blocked: {state['guardrail']['reason']}"],
        "messages": [AIMessage(content=message)],
    }


def output_guardrail(state: TravelState):
    answer = state["messages"][-1].content or "Sorry, I could not produce a travel plan. Please try again."
    notes = []

    answer, redacted = redact_secrets(answer)
    if redacted:
        notes.append(f"Redacted {redacted} secret-like value(s) from the answer.")

    budget_note = budget_check_note(state.get("budget"))
    if budget_note:
        answer = f"{answer}\n\n---\n\n{budget_note}"
        notes.append("Added code-computed budget check.")

    return {"final_answer": answer, "guardrail_notes": notes}
