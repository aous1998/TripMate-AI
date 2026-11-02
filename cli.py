"""Run one travel request from the terminal, including the human review step."""
# -----------------------------------------------------------------------------
# cli.py - the same app as the web page, but in the terminal.
# Usage: python cli.py
# It uses backend.py directly (no web server), so it needs the same .env file.
# -----------------------------------------------------------------------------

# Importing backend runs its startup code (database, graph, MCP server).
from backend import ReviewError, resume_travel_agent, run_travel_agent

# A fixed conversation id for the terminal. Each new run starts a fresh request
# on this thread; an old unanswered review is simply replaced.
THREAD_ID = "cli_user"

# Ask for the trip request and run the graph.
user_input = input("Enter travel request: ")
response = run_travel_agent(user_input=user_input, thread_id=THREAD_ID)

# While the graph is paused for review, show the research and ask the user.
while response["status"] == "needs_review":
    review = response["review"]
    print("\nFLIGHTS:\n", review["flight_results"] or "Not researched.")
    print("\nHOTELS:\n", review["hotel_results"] or "Not researched.")

    # Empty input (just Enter) means "approve"; any text means "change this".
    feedback = input("\nPress Enter to approve, or type the changes you want: ").strip()
    try:
        # approved=not feedback -> True when feedback is empty.
        response = resume_travel_agent(THREAD_ID, approved=not feedback, feedback=feedback)
    except ReviewError as e:
        # e.g. the feedback was blocked by the input guardrail: show why, ask again.
        print(e)

# The graph finished: print the final answer (Markdown text).
print("\nFINAL RESPONSE:\n")
print(response["answer"])
