"""Ice breaker activities shown once before a review session starts."""

import random
from typing import TypedDict


class IceBreaker(TypedDict):
    slug: str
    title: str
    description: str


ICEBREAKERS: list[IceBreaker] = [
    {
        "slug": "i_have_who_has",
        "title": "I Have / Who Has?",
        "description": (
            "Create a chain of index cards where the bottom of one card asks a question, "
            "and the top of the next card has the answer. It encourages active listening "
            "and ensures everyone participates without pressure."
        ),
    },
    {
        "slug": "math_magic",
        "title": "Math Magic (Think of a Number)",
        "description": (
            "Pick a number, double it, add 10, halve it, and subtract your original number. "
            "Everyone gets the same answer (5) — a quick magic trick to wake up your brain "
            "before you start."
        ),
    },
    {
        "slug": "equation_facts",
        "title": "Equation Facts",
        "description": (
            "Write an equation whose solution equals a personal fact about yourself. "
            "For example, x - 2 = 1 to show you have 1 sibling."
        ),
    },
    {
        "slug": "number_fact_pass",
        "title": "Number Fact Pass",
        "description": (
            "State your name and a number's property (e.g., \"49, it's a perfect square\"). "
            "The next person must use that number — or pick a new one — to state a "
            "different property (e.g., \"49, it's an odd number\")."
        ),
    },
]


def icebreaker_for_session(session_pk: int) -> IceBreaker:
    """Return one randomized ice breaker, stable for the same session."""
    rng = random.Random(session_pk)
    return rng.choice(ICEBREAKERS)
