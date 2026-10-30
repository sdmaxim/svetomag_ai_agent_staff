"""
Terminal chat with the support agent. Type 'quit' to stop.

Usage (PowerShell, from the support_agent folder):
    .\\run.ps1 chat
"""
from agent import SupportSession
from answer_check import check_answer


def main():
    session = SupportSession()
    print("Svetomag support (type 'quit' to stop)\n")
    while True:
        try:
            msg = input("You: ").strip()
        except EOFError:
            break
        if msg.lower() in ("quit", "exit", "q"):
            break
        if not msg:
            continue
        blocked_before = session.blocked_drafts
        reply = session.ask(msg)
        print(f"\nAgent: {reply}\n")
        if session.blocked_drafts > blocked_before:   # shown to the developer only, never to a customer
            print(f"  [guardrail] blocked {session.blocked_drafts - blocked_before} wrong draft(s) before this reply")
        for problem in check_answer(reply, session.log):
            print(f"  [CHECK FAILED] {problem}")


if __name__ == "__main__":
    main()
