import re


def pluralize_numbers(text: str) -> str:
    """
    Adds 's' to a word following a number (integer or float)
    if the number is not ±1. Works even if Rich markup tags
    like [/orange1] appear between the number and the word.
    """
    pattern = re.compile(
        r'\b(-?\d+(?:\.\d+)?)'        # number
        r'(?:\[[^\]]+\])*'            # optional Rich tags, e.g. [orange1], [/orange1]
        r'\s+([A-Za-z]+)\b'           # the word itself
    )

    def replacer(match):
        number = float(match.group(1))
        word = match.group(2)
        # add 's' only if not ±1
        if abs(number) != 1:
            # replace only the word part with pluralized one
            return match.group(0)[:-len(word)] + word + "s"
        return match.group(0)

    return pattern.sub(replacer, text)