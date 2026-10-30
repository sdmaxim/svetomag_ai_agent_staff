"""
Admin tool for the difficult-questions loop (a web page replaces it in Step 6).

Usage (PowerShell, from the support_agent folder):
    .\\run.ps1 admin list              # open questions, most asked first
    .\\run.ps1 admin list all          # every question
    .\\run.ps1 admin answer 3 "Delivery in the Netherlands takes 2-3 working days."
    .\\run.ps1 admin reject 4          # not a real question / spam
"""
import sys

from dotenv import load_dotenv

import knowledge

load_dotenv()


def show(items):
    if not items:
        print("(nothing)")
    for q in items:
        print(f"#{q['id']:<3} [{q['status']:8}] asked {q['times_asked']}x  last {q['last_asked_at']}")
        print(f"      Q: {q['question']}")
        if q.get("reason"):
            print(f"      why the agent could not answer: {q['reason']}")
        if q.get("answer"):
            print(f"      A: {q['answer']}")


def main():
    args = sys.argv[1:]
    if not args or args[0] == "list":
        items = knowledge.load()
        if not (len(args) > 1 and args[1] == "all"):
            items = [q for q in items if q["status"] == "open"]
        show(sorted(items, key=lambda q: (-q["times_asked"], q["id"])))
    elif args[0] == "answer" and len(args) >= 3:
        q = knowledge.answer_question(int(args[1]), " ".join(args[2:]))
        print(f"answered #{q['id']}: the agent will use this answer from now on")
    elif args[0] == "reject" and len(args) == 2:
        q = knowledge.reject_question(int(args[1]))
        print(f"rejected #{q['id']}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
