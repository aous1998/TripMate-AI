from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.common import describe_trip, mark_done
from llm import get_llm
from state import BudgetEstimate, TravelState
from tools.currency_tool import convert_currency


def budget_agent(state: TravelState):
    trip = state.get("trip") or {}
    budget_eur, conversion_note = user_budget_in_eur(trip)

    prompt = f"""
Estimate the total cost of this trip in EUR, for all travelers.

Trip Details:
{describe_trip(trip)}

Flights:
{state.get('flight_results') or 'Not researched.'}

Hotels:
{state.get('hotel_results') or 'Not researched.'}

Itinerary:
{state.get('itinerary') or 'Not planned.'}

Give one line per category (Flights, Accommodation, Food, Local transport, Activities,
and anything else significant). Use realistic current prices for the destination.
"""

    try:
        estimate = get_llm().with_structured_output(BudgetEstimate).invoke([
            SystemMessage(content="You are a careful travel budget analyst."),
            HumanMessage(content=prompt),
        ])
        # The model itemises; the total is computed here so it always adds up.
        total = round(sum(line.amount_eur for line in estimate.lines), 2)
        budget = {
            "lines": [line.model_dump() for line in estimate.lines],
            "total_eur": total,
            "budget_eur": budget_eur,
            "within_budget": None if budget_eur is None else total <= budget_eur,
            "assumptions": estimate.assumptions,
            "conversion_note": conversion_note,
        }
        note = f"Budget estimated: {total:.0f} EUR."
    except Exception as e:
        print("Budget agent could not build an estimate:", e)
        budget = {"error": "A structured budget estimate was not available."}
        note = "Budget estimate unavailable."

    return {
        "budget": budget,
        "completed": mark_done(state, "budget_agent"),
        "messages": [AIMessage(content=note)],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def user_budget_in_eur(trip: dict) -> tuple[float | None, str]:
    """The user's budget converted to EUR, plus a note on any conversion."""
    amount = trip.get("budget")
    currency = (trip.get("currency") or "EUR").upper()

    if not amount:
        return None, ""

    if currency == "EUR":
        return float(amount), ""

    try:
        converted = convert_currency(amount, currency, "EUR")
        return converted, f"{amount:g} {currency} is about {converted:.0f} EUR at today's ECB rate."
    except Exception as e:
        print("Currency conversion failed:", e)
        return None, f"Could not convert {amount:g} {currency} to EUR."


def format_budget(budget: dict | None) -> str:
    """Render the budget estimate as a markdown table for the responder."""
    if not budget:
        return "Not estimated."
    if budget.get("error"):
        return budget["error"]

    rows = ["| Category | Estimate (EUR) | Basis |", "| --- | ---: | --- |"]
    for line in budget["lines"]:
        rows.append(f"| {line['category']} | {line['amount_eur']:.0f} | {line.get('note', '')} |")
    rows.append(f"| **Total** | **{budget['total_eur']:.0f}** | |")

    extra = [budget.get("assumptions", "")]
    if budget.get("conversion_note"):
        extra.append(budget["conversion_note"])
    if budget.get("budget_eur") is not None:
        status = "within" if budget["within_budget"] else "OVER"
        extra.append(f"User budget: {budget['budget_eur']:.0f} EUR. The estimate is {status} budget.")

    return "\n".join(rows) + "\n\n" + "\n".join(e for e in extra if e)
