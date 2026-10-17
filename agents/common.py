"""Helpers shared by the agents."""


def describe_trip(trip: dict | None) -> str:
    """Turn the supervisor's extracted trip details into prompt-ready lines."""
    if not trip:
        return "No structured trip details were extracted."

    lines = []

    if trip.get("origin"):
        lines.append(f"- Origin: {trip['origin']}")
    if trip.get("destination"):
        lines.append(f"- Destination: {trip['destination']}")
    if trip.get("duration_days"):
        lines.append(f"- Duration: {trip['duration_days']} days")
    if trip.get("budget"):
        lines.append(f"- Budget: {trip['budget']:g} {trip.get('currency') or 'EUR'}")
    if trip.get("travelers"):
        lines.append(f"- Travelers: {trip['travelers']}")
    if trip.get("interests"):
        lines.append(f"- Interests: {', '.join(trip['interests'])}")

    return "\n".join(lines) or "No structured trip details were extracted."


def mark_done(state: dict, agent_name: str) -> list[str]:
    """Return the completed-agents list with this agent appended."""
    return state.get("completed", []) + [agent_name]
