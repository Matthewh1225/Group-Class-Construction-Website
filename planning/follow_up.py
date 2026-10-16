import re

MAX_QUESTIONS = 3

def question_key(question):
    # Ignore case and punctuation, keeping measurements and object names.
    return " ".join(re.findall(r"\w+", question.casefold()))


def pending_questions(questions, answers):
    seen = set()
    for answer in answers:
        seen.add(question_key(answer.get("question", "")))
    pending = []
    for question in questions:
        question = question.strip()
        key = question_key(question)
        if not key or key in seen:
            continue
        pending.append(question)
        seen.add(key)
    return pending


def unresolved_questions(questions, answers):
    # Skipped answers stop another question round, but do not resolve missing scope.
    unknown_answers = {
        "", "not sure", "unsure", "unknown", "skip", "skipped", "i don t know",
        "i dont know", "not provided", "not sure use reasonable planning assumptions where possible",
    }
    known_answers = []
    for answer in answers:
        value = answer.get("answer", "")
        if isinstance(value, str) and question_key(value) not in unknown_answers:
            known_answers.append(answer)
    return pending_questions(questions, known_answers)
