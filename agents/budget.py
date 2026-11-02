# -----------------------------------------------------------------------------
# agents/budget.py - the budget specialist (runs last, after the itinerary).
#
#   budget_agent()       asks the LLM for an itemised BudgetEstimate, then adds
#                        up the total in Python (LLMs are bad at arithmetic)
#   user_budget_in_eur() converts the user's budget to EUR with the currency tool
#   format_budget()      turns the result into a Markdown table for the responder
# -----------------------------------------------------------------------------

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.common import UNTRUSTED_DATA_RULE, as_data, describe_trip, mark_done
from llm import get_llm
from state import BudgetEstimate, TravelState
from tools import mcp_client


def budget_agent(state: TravelState):
    trip = state.get("trip") or {}
    # e.g. 2000 USD -> (about 1850.0, "2000 USD is about 1850 EUR at today's ECB rate.")
    budget_eur, conversion_note = user_budget_in_eur(trip)

    # The prompt gives the LLM everything found so far. Tool results are wrapped
    # with as_data(...) so instructions hidden inside them are not followed.
    prompt = f"""
Estimate the total cost of this trip in EUR, for all travelers.

Trip Details:
{describe_trip(trip)}

Flights:
{as_data('flights', state.get('flight_results'), empty='Not researched.')}

Hotels:
{as_data('hotels', state.get('hotel_results'), empty='Not researched.')}

Itinerary:
{as_data('itinerary', state.get('itinerary'), empty='Not planned.')}

Give one line per category (Flights, Accommodation, Food, Local transport, Activities,
and anything else significant). Use realistic current prices for the destination.
"""

    try:
        # Structured output: the answer must match BudgetEstimate (state.py),
        # i.e. a list of {category, amount_eur, note} lines plus assumptions.
        estimate = get_llm().with_structured_output(BudgetEstimate).invoke([
            SystemMessage(content=f"You are a careful travel budget analyst. {UNTRUSTED_DATA_RULE}"),
            HumanMessage(content=prompt),
        ])
        # The model itemises; the total is computed here so it always adds up.
        total = round(sum(line.amount_eur for line in estimate.lines), 2)
        budget = {
            "lines": [line.model_dump() for line in estimate.lines],   # objects -> dicts
            "total_eur": total,
            "budget_eur": budget_eur,               # None if the user gave no budget
            # True/False compared with the user's budget; None if there is no budget.
            "within_budget": None if budget_eur is None else total <= budget_eur,
            "assumptions": estimate.assumptions,
            "conversion_note": conversion_note,
        }
        note = f"Budget estimated: {total:.0f} EUR."
    except Exception as e:
        # The LLM call failed: store an error instead, so the rest of the answer still works.
        print("Budget agent could not build an estimate:", e)
        budget = {"error": "A structured budget estimate was not available."}
        note = "Budget estimate unavailable."

    # The state changes this agent returns.
    return {
        "budget": budget,
        "completed": mark_done(state, "budget_agent"),   # tells the supervisor this step is done
        "messages": [AIMessage(content=note)],           # short log line in the chat history
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def user_budget_in_eur(trip: dict) -> tuple[float | None, str]:
    """The user's budget converted to EUR, plus a note on any conversion."""
    amount = trip.get("budget")
    currency = (trip.get("currency") or "EUR").upper()

    # No budget given: nothing to compare against.
    if not amount:
        return None, ""

    # Already in EUR: no conversion needed.
    if currency == "EUR":
        return float(amount), ""

    try:
        # Ask the MCP currency tool (Frankfurter / ECB rates) to convert.
        converted = float(mcp_client.call_tool(
            "convert_currency", amount=amount, from_currency=currency, to_currency="EUR",
        ))
        return converted, f"{amount:g} {currency} is about {converted:.0f} EUR at today's ECB rate."
    except Exception as e:
        # Unknown currency or the rate service is down: skip the budget check.
        print("Currency conversion failed:", e)
        return None, f"Could not convert {amount:g} {currency} to EUR."


def format_budget(budget: dict | None) -> str:
    """Render the budget estimate as a markdown table for the responder."""
    if not budget:
        return "Not estimated."
    if budget.get("error"):
        return budget["error"]

    # Markdown table header. "---:" right-aligns the numbers column.
    rows = ["| Category | Estimate (EUR) | Basis |", "| --- | ---: | --- |"]
    for line in budget["lines"]:
        rows.append(f"| {line['category']} | {line['amount_eur']:.0f} | {line.get('note', '')} |")
    rows.append(f"| **Total** | **{budget['total_eur']:.0f}** | |")

    # Extra sentences under the table: assumptions, conversion, verdict.
    extra = [budget.get("assumptions", "")]
    if budget.get("conversion_note"):
        extra.append(budget["conversion_note"])
    if budget.get("budget_eur") is not None:
        status = "within" if budget["within_budget"] else "OVER"
        extra.append(f"User budget: {budget['budget_eur']:.0f} EUR. The estimate is {status} budget.")

    # Table, a blank line, then the non-empty extra sentences.
    return "\n".join(rows) + "\n\n" + "\n".join(e for e in extra if e)
