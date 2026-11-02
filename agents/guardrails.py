"""Input and output guardrails.

Input:  rule-based checks run before any LLM call (length, prompt injection,
        card numbers). Off-topic requests are caught by the supervisor's
        structured output (SupervisorDecision.is_travel_request).
Output: secrets are redacted and the budget check is computed in code, so
        the final answer never relies on the LLM's arithmetic.
"""
# -----------------------------------------------------------------------------
# agents/guardrails.py - safety checks at the start and the end of the graph.
#
# The file has two halves:
#   1. plain helper functions (check_input, luhn_valid, redact_secrets, ...)
#      that are easy to unit-test (tests/test_guardrails.py);
#   2. the graph nodes (input_guardrail, route_after_input, blocked_response,
#      output_guardrail) that use those helpers.
# -----------------------------------------------------------------------------

import re   # regular expressions: text patterns

from langchain_core.messages import AIMessage

from state import TravelState


# Longest request we accept (longer text is usually pasted documents or an attack).
MAX_INPUT_CHARS = 1500

# Regular expressions for common prompt-injection phrases.
# Reading aid:  \b = word boundary,  (a|b) = a or b,  .{0,30} = up to 30 any characters,
#               \s+ = one or more spaces,  s? = optional "s".
INJECTION_PATTERNS = [
    # "ignore all previous instructions", "forget your rules", ...
    r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|your|all)\b.{0,20}\b(instructions?|prompts?|rules)\b",
    # "reveal the system prompt", "print your hidden instructions", ...
    r"\b(reveal|show|print|repeat|leak)\b.{0,30}\b(system|hidden|initial)\s+(prompt|instructions?)",
    # any mention of "system prompt"
    r"\bsystem\s+prompt\b",
    # well-known jailbreak names
    r"\b(jailbreak|DAN mode|developer mode)\b",
    # "act as an unfiltered AI", ...
    r"\bact as\b.{0,20}\b(unfiltered|unrestricted|uncensored)\b",
]

# Patterns for secrets that must never appear in an answer.
SECRET_PATTERNS = [
    r"\bgsk_[A-Za-z0-9]{20,}",                    # Groq
    r"\btvly-[A-Za-z0-9-]{20,}",                  # Tavily
    r"\bsk-[A-Za-z0-9_-]{20,}",                   # OpenAI-style keys
    # This one has two groups in brackets: group 1 = "postgresql://user:",
    # group 2 = "@". The password between them is what gets replaced.
    r"(postgres(?:ql)?://[^:\s/]+:)[^@\s]+(@)",   # database password in a URL
]

# The text the user sees for each block reason (reason -> message).
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
    # `text or ""` guards against None; strip() removes spaces at both ends.
    text = (text or "").strip()

    if not text:
        return "empty"
    if len(text) > MAX_INPUT_CHARS:
        return "too_long"
    # any(...) is True if at least one pattern matches (case-insensitive).
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in INJECTION_PATTERNS):
        return "prompt_injection"
    if contains_card_number(text):
        return "card_number"

    # None = no problem found, the request may continue.
    return None


def contains_card_number(text: str) -> bool:
    # Find runs of 13-19 digits, optionally separated by spaces or dashes
    # ("4111 1111 1111 1111", "4111-1111-...").
    for match in re.finditer(r"\b(?:\d[ -]?){13,19}\b", text):
        # Keep only the digits ("\D" = any non-digit).
        digits = re.sub(r"\D", "", match.group())
        # Real card numbers pass the Luhn checksum; random long numbers
        # (phone numbers, booking codes) usually do not.
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            return True
    return False


def luhn_valid(digits: str) -> bool:
    # The Luhn algorithm (checksum used by all payment cards):
    # from the right, double every second digit; if the result is > 9,
    # subtract 9; add everything up; valid if the sum ends in 0.
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:                      # every second digit from the right
            n = n * 2 - 9 if n > 4 else n * 2   # n > 4 means n*2 > 9
        total += n
    return total % 10 == 0


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace anything that looks like an API key or DB password. Returns (text, count)."""
    count = 0
    for pattern in SECRET_PATTERNS:
        def replace(match):
            # Keep the URL around a database password, drop only the password.
            # match.lastindex == 2 means the pattern had two groups (the database URL one).
            if match.lastindex == 2:
                return f"{match.group(1)}[redacted]{match.group(2)}"
            return "[redacted]"

        # re.subn replaces every match and also returns how many it replaced.
        text, n = re.subn(pattern, replace, text)
        count += n
    return text, count


def budget_check_note(budget: dict | None) -> str:
    """A budget verdict computed from the itemised estimate, not written by the LLM."""
    # No note when there is no budget, it failed, or the user gave no budget.
    if not budget or budget.get("error") or budget.get("budget_eur") is None:
        return ""

    total = budget["total_eur"]     # sum of the lines, computed in agents/budget.py
    limit = budget["budget_eur"]    # the user's budget converted to EUR

    # {x:,.0f} formats 2345.6 as "2,346" (thousands separator, no decimals).
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
    # First node of every run. Records whether the request is blocked and why;
    # route_after_input() reads this to choose the next node.
    reason = check_input(state["user_query"])
    if reason:
        return {"guardrail": {"blocked": True, "reason": reason}}
    return {"guardrail": {"blocked": False, "reason": ""}}


def route_after_input(state: TravelState) -> str:
    # Conditional edge after input_guardrail: blocked -> refusal, otherwise -> supervisor.
    return "blocked_response" if state["guardrail"]["blocked"] else "supervisor"


def blocked_response(state: TravelState):
    # Answer a blocked request with the fixed message for its reason.
    # No LLM is involved, so an attacker cannot talk their way past it.
    message = BLOCK_MESSAGES[state["guardrail"]["reason"]]
    return {
        "final_answer": message,
        "guardrail_notes": [f"Request blocked: {state['guardrail']['reason']}"],
        "messages": [AIMessage(content=message)],
    }


def output_guardrail(state: TravelState):
    # Last node of a normal run. The responder's answer is the newest message.
    answer = state["messages"][-1].content or "Sorry, I could not produce a travel plan. Please try again."
    notes = []   # what this guardrail changed (shown in logs/tests, not to the user)

    # 1. Remove anything that looks like an API key or database password.
    answer, redacted = redact_secrets(answer)
    if redacted:
        notes.append(f"Redacted {redacted} secret-like value(s) from the answer.")

    # 2. Append a budget verdict computed in Python (the LLM's maths is not trusted).
    budget_note = budget_check_note(state.get("budget"))
    if budget_note:
        answer = f"{answer}\n\n---\n\n{budget_note}"   # "---" draws a line in Markdown
        notes.append("Added code-computed budget check.")

    # final_answer is what backend.build_response() sends to the browser.
    return {"final_answer": answer, "guardrail_notes": notes}
