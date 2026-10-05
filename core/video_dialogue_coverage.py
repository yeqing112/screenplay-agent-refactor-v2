"""Deterministic dialogue coverage and provider occurrence audits.

The model independent IR may keep the complete authoritative line.  A provider
prompt is allowed to emit that line only through its timed phrase blocks.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


@dataclass(frozen=True)
class DialoguePhraseCoverageAudit:
    authoritative_text: str
    phrase_windows: tuple[dict[str, Any], ...]
    phrase_count: int
    concatenated_text: str
    missing_text: str
    duplicated_text: tuple[str, ...]
    out_of_order: bool
    coverage_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "authoritative_text": self.authoritative_text,
            "phrase_windows": [dict(x) for x in self.phrase_windows],
            "phrase_count": self.phrase_count,
            "concatenated_text": self.concatenated_text,
            "missing_text": self.missing_text,
            "duplicated_text": list(self.duplicated_text),
            "out_of_order": self.out_of_order,
            "coverage_status": self.coverage_status,
        }


class DialogueCoverageError(ValueError):
    def __init__(self, code: str, audit: DialoguePhraseCoverageAudit):
        super().__init__(code)
        self.code = code
        self.audit = audit


def audit_dialogue_phrase_coverage(
    authoritative_text: str,
    phrase_windows: Sequence[Mapping[str, Any]],
) -> DialoguePhraseCoverageAudit:
    """Audit exact phrase concatenation, duplicates, omissions and order."""
    windows = tuple(dict(x) for x in phrase_windows if isinstance(x, Mapping))
    ordered = tuple(sorted(windows, key=lambda x: (float(x.get("start_time", 0)), float(x.get("end_time", 0)))))
    texts = tuple(str(x.get("text") or "") for x in ordered)
    counts: dict[str, int] = {}
    for text in texts:
        counts[text] = counts.get(text, 0) + 1
    duplicated = tuple(text for text, count in counts.items() if text and count > 1)
    concatenated = "".join(texts)
    canonical = _norm(authoritative_text)
    joined = _norm(concatenated)
    missing = ""
    # Phrase windows are ordered by their declared time.  A repeated phrase is
    # duplication.  If supplied phrases are a subsequence of the canonical
    # line, the failure is an omission; a decreasing canonical offset is an
    # order error.
    offsets: list[int] = []
    for text in texts:
        offset = canonical.find(_norm(text)) if text else -1
        offsets.append(offset)
    if joined != canonical and not duplicated:
        covered: list[tuple[int, int]] = [(offset, offset + len(_norm(text))) for offset, text in zip(offsets, texts) if offset >= 0 and text]
        covered.sort()
        cursor = 0
        gaps: list[str] = []
        for start, end in covered:
            if start > cursor:
                gaps.append(canonical[cursor:start])
            cursor = max(cursor, end)
        if cursor < len(canonical):
            gaps.append(canonical[cursor:])
        missing = "".join(gaps) or canonical
    out_of_order = bool(joined != canonical and not duplicated and any(offsets[i] > offsets[i + 1] >= 0 for i in range(len(offsets) - 1)))
    if duplicated:
        status = "DUPLICATION"
    elif out_of_order:
        status = "ORDER_MISMATCH"
    elif joined != canonical:
        status = "INCOMPLETE"
    else:
        status = "PASS"
    audit = DialoguePhraseCoverageAudit(
        authoritative_text=str(authoritative_text or ""),
        phrase_windows=ordered,
        phrase_count=len(ordered),
        concatenated_text=concatenated,
        missing_text=missing,
        duplicated_text=duplicated,
        out_of_order=out_of_order,
        coverage_status=status,
    )
    if duplicated:
        raise DialogueCoverageError("DIALOGUE_PHRASE_DUPLICATION", audit)
    if out_of_order:
        raise DialogueCoverageError("DIALOGUE_PHRASE_ORDER_MISMATCH", audit)
    if joined != canonical:
        raise DialogueCoverageError("DIALOGUE_PHRASE_COVERAGE_INCOMPLETE", audit)
    return audit


def audit_provider_dialogue_occurrences(
    prompt: str,
    authoritative_text: str,
    phrase_windows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Require one audible occurrence per phrase and zero plain full-line copies."""
    blocks = re.findall(r"<d>.*?</d>", prompt, flags=re.DOTALL)
    phrase_audits: list[dict[str, Any]] = []
    errors: list[str] = []
    for window in phrase_windows:
        phrase = str(window.get("text") or "")
        total = prompt.count(phrase) if phrase else 0
        inside = sum(block.count(phrase) for block in blocks)
        outside = total - inside
        item = {"text": phrase, "total_occurrences": total, "inside_d_occurrences": inside, "outside_d_occurrences": outside}
        phrase_audits.append(item)
        if total != 1 or inside != 1 or outside != 0:
            errors.append("H3_DIALOGUE_DUPLICATE_EMISSION")
    full_count = prompt.count(str(authoritative_text or "")) if authoritative_text else 0
    result = {
        "phrase_occurrences": phrase_audits,
        "plain_full_authoritative_occurrence": full_count,
        "d_block_count": len(blocks),
        "status": "PASS" if not errors and full_count == 0 else "FAIL",
        "errors": sorted(set(errors + (["H3_DIALOGUE_DUPLICATE_EMISSION"] if full_count else []))),
    }
    if result["status"] != "PASS":
        raise ValueError(result["errors"][0])
    return result
