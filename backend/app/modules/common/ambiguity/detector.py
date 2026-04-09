import re

LAW_KEYWORDS = [
    "zákoník práce",
    "občanský zákoník",
    "trestní zákoník",
    "zákon o",
    "sb."
]

PARAGRAPH_PATTERN = r"^§\s*\d+[a-zA-Z]*$"


def is_paragraph_only(query: str) -> bool:
    q = query.lower().strip()

    if not re.match(PARAGRAPH_PATTERN, q):
        return False

    for kw in LAW_KEYWORDS:
        if kw in q:
            return False

    return True
