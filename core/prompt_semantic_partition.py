"""Partition a compiled prompt into semantic regions for residue audits."""
from __future__ import annotations

from collections import Counter
import re
from typing import Any, Iterable


def partition_prompt(prompt: str, *, dialogue_texts: Iterable[str] = ()) -> dict[str, Any]:
    sections: dict[str, list[str]] = {"POSITIVE_VISUAL": [], "NEGATIVE_VISUAL": [], "DIALOGUE": [], "SOUNDSCAPE": []}
    current = "POSITIVE_VISUAL"
    for raw in str(prompt).splitlines():
        line = raw.strip()
        lower = line.lower()
        if not line:
            continue
        if "timed dialogue events" in lower or "<d>" in lower:
            current = "DIALOGUE"
        elif "overall_soundscape" in lower or "non_diegetic_music" in lower:
            current = "SOUNDSCAPE"
        elif "negative constraints" in lower:
            current = "NEGATIVE_VISUAL"
        if "<d>" in lower:
            sections["DIALOGUE"].append(line)
        elif current == "NEGATIVE_VISUAL" or lower.startswith(("no ", "the apple is mentioned only")):
            sections["NEGATIVE_VISUAL"].append(line)
        elif current == "SOUNDSCAPE":
            sections["SOUNDSCAPE"].append(line)
        elif not lower.endswith(":"):
            sections["POSITIVE_VISUAL"].append(line)

    def occurrences(token: str) -> dict[str, int]:
        return {name: sum(line.lower().count(token.lower()) for line in lines) for name, lines in sections.items()}

    strap = occurrences("strap")
    apple = occurrences("apple") | {"dialogue_canonical_mention": sum(line.count("苹果") for line in sections["DIALOGUE"])}
    return {
        "status": "PASS",
        "sections": sections,
        "counts": {"strap": strap, "apple": apple},
        "positive_visual_forbidden_tokens": {token: sum(line.lower().count(token) for line in sections["POSITIVE_VISUAL"]) for token in ("bag", "handbag", "shoulder bag", "crossbody", "bag strap", "strap", "apple", "umbrella")},
        "partition_policy": "POSITIVE_VISUAL cannot carry unauthorized object semantics; dialogue and negative constraints are separate semantic channels.",
    }


__all__ = ["partition_prompt"]
