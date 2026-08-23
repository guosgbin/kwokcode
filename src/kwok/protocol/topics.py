from __future__ import annotations

import re

_SEGMENT_RE = re.compile(r"^[a-z0-9_-]+$")


class InvalidTopicPatternError(ValueError):
    pass


def validate_pattern(pattern: str) -> None:
    if not pattern:
        raise InvalidTopicPatternError("订阅模式不能为空")
    segments = pattern.split(".")
    if any(not segment for segment in segments):
        raise InvalidTopicPatternError(f"订阅模式含空段：{pattern!r}")
    for index, segment in enumerate(segments):
        if segment in ("*", "**"):
            if segment == "**" and index != len(segments) - 1:
                raise InvalidTopicPatternError(f"`**` 仅允许作为末段：{pattern!r}")
            continue
        if _SEGMENT_RE.match(segment) is None:
            raise InvalidTopicPatternError(f"订阅模式含非法字符：{segment!r}")


def match(pattern: str, topic: str) -> bool:
    if pattern == "*":
        return True
    pat_segments = pattern.split(".")
    topic_segments = topic.split(".")
    topic_index = 0
    for segment in pat_segments:
        if segment == "**":
            return True
        if segment == "*":
            if topic_index >= len(topic_segments):
                return False
            topic_index += 1
            continue
        if topic_index >= len(topic_segments) or topic_segments[topic_index] != segment:
            return False
        topic_index += 1
    return topic_index == len(topic_segments)
