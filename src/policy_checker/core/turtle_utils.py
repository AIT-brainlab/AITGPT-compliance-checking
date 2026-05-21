from __future__ import annotations

import re

_RULE_MARKER = re.compile(r"# Rule:\s+(AIT-\d+)")


def split_rule_blocks(ttl_text: str) -> dict[str, str]:
    """Map AIT rule ids to their generated Turtle block."""
    blocks: dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []

    for line in ttl_text.splitlines():
        match = _RULE_MARKER.match(line)
        if match:
            if current_id and current_lines:
                blocks[current_id] = "\n".join(current_lines).strip()
            current_id = match.group(1)
            current_lines = [line]
        elif current_id:
            current_lines.append(line)

    if current_id and current_lines:
        blocks[current_id] = "\n".join(current_lines).strip()

    return blocks


def get_rule_block(ttl_text: str, rule_id: str) -> str:
    return split_rule_blocks(ttl_text).get(rule_id, "")


def prefix_block(ttl_text: str) -> str:
    marker_index = ttl_text.find("# Rule:")
    return ttl_text[:marker_index] if marker_index >= 0 else ttl_text
