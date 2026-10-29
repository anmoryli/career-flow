"""Presentation cleanup for AI replacement text; never applied to user-authored edits."""

import re

INTRO = re.compile(
    r"^(?:(?:此外|另外|除此之外|同时)[，,：:]\s*|(?:建议写法|改写后|优化后)[：:]\s*)"
)


def ready_to_insert(value):
    value = value.strip()
    while INTRO.match(value):
        value = INTRO.sub("", value, count=1).lstrip()
    if not value:
        raise ValueError("AI 未返回可直接使用的正文")
    return value
