"""Run one travel request from the terminal, including the human review step."""

from backend import ReviewError, resume_travel_agent, run_travel_agent

THREAD_ID = "cli_user"

user_input = input("Enter travel request: ")
response = run_travel_agent(user_input=user_input, thread_id=THREAD_ID)

while response["status"] == "needs_review":
    review = response["review"]
    print("\nFLIGHTS:\n", review["flight_results"] or "Not researched.")
    print("\nHOTELS:\n", review["hotel_results"] or "Not researched.")

    feedback = input("\nPress Enter to approve, or type the changes you want: ").strip()
    try:
        response = resume_travel_agent(THREAD_ID, approved=not feedback, feedback=feedback)
    except ReviewError as e:
        print(e)

print("\nFINAL RESPONSE:\n")
print(response["answer"])
