"""QA Agent with resilient structured-output handling."""

from __future__ import annotations

import json
import logging
import re

import config
from agents.base import BaseAgent
from core import safe_json_loads
from core.llm import call_llm
from core.production_skill import (
    build_production_skill_prompt_block,
    build_script_skill_execution_plan,
    classify_script_qa_repair_stage,
    classify_script_qa_rule_family,
    classify_script_qa_structure_layer,
)
from core.prompts import load_prompt
from core.structured_output import parse_json_object, strip_code_fences, write_debug_output
from models import Book, BookBible, CharacterProfile, QAResult, Script

logger = logging.getLogger(__name__)


def _qa_issue_items(result: dict) -> list[dict]:
    if not isinstance(result, dict):
        return []
    issues = result.get("issues")
    if isinstance(issues, list):
        return issues
    errors = result.get("errors")
    if isinstance(errors, list):
        return errors
    return []


class QAAgent(BaseAgent):
    """Episode script QA agent."""

    name = "qa"

    ANALYSIS_MARKERS = (
        "我们需要回答用户",
        "需要仔细分析剧本",
        "let me analyze",
        "the user wants me",
        "current episode script",
        "need to check the script",
    )
    SEVERITY_SCORES = {
        "high": 2.0,
        "medium": 1.0,
        "low": 0.35,
    }
    STRUCTURE_LAYER_SUMMARY_ORDER = (
        "fact_layer",
        "scene_execution_layer",
        "compiler_layer",
    )

    def _build_character_bible_excerpt(self, bible_content: str) -> str:
        char_info = ""
        lines = (bible_content or "").split("\n")
        in_char_section = False
        for line in lines:
            if "## 一、人物数据库" in line:
                in_char_section = True
            elif line.startswith("## ") and in_char_section:
                break
            elif in_char_section:
                char_info += line + "\n"
        return char_info

    def _build_portrait_info(self, session) -> str:
        portrait_info = ""
        try:
            portraits = session.query(CharacterProfile).filter(
                CharacterProfile.book_id == self.book_id
            ).all()
            for portrait in portraits:
                portrait_info += f"\n### {portrait.name}\n"
                portrait_info += f"性别: {portrait.gender} | 年龄: {portrait.age_range}\n"
                portrait_info += f"脸型: {portrait.face_shape} | 五官: {portrait.facial_features}\n"
                portrait_info += f"体型: {portrait.body_type} | 肤色: {portrait.skin_tone}\n"
                portrait_info += f"穿着: {portrait.signature_outfit}\n"
                portrait_info += f"气质: {portrait.temperament} | 氛围: {portrait.vibe}\n"
                portrait_info += f"说话风格: {portrait.speech_style}\n"
                portrait_info += f"体态: {portrait.body_language}\n"
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load character profiles: %s", exc)
        return portrait_info or "(暂无画像数据)"

    def _build_prompt(self, *, episode: int, bible_chars: str, portrait_info: str, script_content: str) -> str:
        prompt = load_prompt(
            "qa/qa",
            bible_chars=bible_chars[:config.CHAR_INFO_CHARS],
            portrait_info=portrait_info[:config.PORTRAIT_EXCERPT_CHARS],
            episode=episode,
            script=script_content[:5000],
        )
        skill_block = build_production_skill_prompt_block(self.book_id, "qa")
        execution_plan = build_script_skill_execution_plan(self.book_id, episode_outline={"episode": episode})
        structure_focus = execution_plan.get("structure_focus", {}) if isinstance(execution_plan, dict) else {}
        focus_block = (
            "## QA Structure Focus\n"
            "Classify issues by structure layer and repair stage whenever possible.\n"
            "- structure_layer must lean toward one of: `fact_layer`, `scene_execution_layer`, `compiler_layer`.\n"
            "- repair_stage must lean toward one of: `fact_generation`, `scene_execution`, `screenplay_compile`, `structure_qa`.\n"
            f"- Current dominant layer hint: {str(structure_focus.get('dominant_layer') or 'none')}\n"
            f"- Current dominant repair stage hint: {str(structure_focus.get('dominant_stage') or 'none')}\n"
            "- If a problem is about identity, prop custody, helper motive, state transition, or impossible body logic, prefer fact-layer reasoning.\n"
            "- If a problem is about missing on-screen proof, weak scene delta, or unfulfilled visual evidence, prefer scene-execution reasoning.\n"
            "- If a problem is about hook strength, truncation, or formatting completeness, prefer compiler-layer reasoning.\n"
        )
        return f"{skill_block}\n\n{focus_block}\n\n{prompt}"

    def _parse_qa_payload(self, raw: str) -> dict:
        payload = parse_json_object(raw, label="qa payload", required_keys={"issues", "errors"})
        issues = payload.get("issues")
        errors = payload.get("errors")
        if issues is None and errors is None:
            raise ValueError("QA payload missing both issues and errors fields.")
        if issues is not None and not isinstance(issues, list):
            raise ValueError("QA payload issues must be a list.")
        if errors is not None and not isinstance(errors, list):
            raise ValueError("QA payload errors must be a list.")
        if "overall_score" in payload:
            try:
                int(payload.get("overall_score"))
            except (TypeError, ValueError):
                raise ValueError("QA payload overall_score must be numeric.")
        return self._normalize_qa_payload(payload)

    def _estimate_overall_score(self, issues: list[dict], errors: list[dict]) -> int:
        penalty = 0.0
        for item in list(issues or []) + list(errors or []):
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity") or "").strip().lower()
            penalty += self.SEVERITY_SCORES.get(severity, 0.6)
        if penalty <= 0:
            return 9
        if penalty <= 1:
            return 8
        if penalty <= 2.5:
            return 7
        if penalty <= 4:
            return 6
        if penalty <= 6:
            return 5
        return 4

    def _normalize_qa_payload(self, payload: dict) -> dict:
        normalized = dict(payload or {})
        issues = normalized.get("issues")
        errors = normalized.get("errors")
        normalized["issues"] = self._annotate_issue_structure_fields(issues if isinstance(issues, list) else [])
        normalized["errors"] = self._annotate_issue_structure_fields(errors if isinstance(errors, list) else [])
        suggestions = normalized.get("suggestions")
        if isinstance(suggestions, list):
            normalized["suggestions"] = [str(item).strip() for item in suggestions if str(item).strip()]
        else:
            normalized["suggestions"] = []
        if "word_count_ok" not in normalized:
            normalized["word_count_ok"] = True
        else:
            normalized["word_count_ok"] = bool(normalized.get("word_count_ok"))
        if "overall_score" not in normalized:
            normalized["overall_score"] = self._estimate_overall_score(normalized["issues"], normalized["errors"])
        else:
            normalized["overall_score"] = int(normalized["overall_score"])
        normalized["structure_summary"] = self._build_structure_summary(normalized["issues"], normalized["errors"])
        return normalized

    def _annotate_issue_structure_fields(self, items: list[dict]) -> list[dict]:
        annotated: list[dict] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            normalized["rule_family"] = classify_script_qa_rule_family(normalized)
            normalized["structure_layer"] = classify_script_qa_structure_layer(normalized)
            normalized["repair_stage"] = classify_script_qa_repair_stage(normalized)
            annotated.append(normalized)
        return annotated

    def _build_structure_summary(self, issues: list[dict], errors: list[dict]) -> dict:
        counts = {key: 0 for key in self.STRUCTURE_LAYER_SUMMARY_ORDER}
        stage_counts: dict[str, int] = {}
        for item in list(issues or []) + list(errors or []):
            if not isinstance(item, dict):
                continue
            layer = str(item.get("structure_layer") or "").strip()
            stage = str(item.get("repair_stage") or "").strip()
            if layer in counts:
                counts[layer] += 1
            if stage:
                stage_counts[stage] = stage_counts.get(stage, 0) + 1
        dominant_layer = max(counts.items(), key=lambda pair: pair[1])[0] if any(counts.values()) else ""
        dominant_stage = max(stage_counts.items(), key=lambda pair: pair[1])[0] if stage_counts else ""
        return {
            "layer_counts": counts,
            "dominant_layer": dominant_layer,
            "stage_counts": stage_counts,
            "dominant_stage": dominant_stage,
        }

    def _extract_json_array_objects(self, text: str, key: str) -> list[dict]:
        marker = f'"{key}"'
        marker_index = text.find(marker)
        if marker_index < 0:
            return []
        array_start = text.find("[", marker_index)
        if array_start < 0:
            return []

        items: list[dict] = []
        index = array_start + 1
        source = text
        while index < len(source):
            char = source[index]
            if char == "{":
                depth = 0
                in_string = False
                escape = False
                for end in range(index, len(source)):
                    current = source[end]
                    if in_string:
                        if escape:
                            escape = False
                        elif current == "\\":
                            escape = True
                        elif current == '"':
                            in_string = False
                        continue
                    if current == '"':
                        in_string = True
                        continue
                    if current == "{":
                        depth += 1
                        continue
                    if current == "}":
                        depth -= 1
                        if depth == 0:
                            fragment = source[index:end + 1]
                            try:
                                payload = parse_json_object(fragment, label=f"qa {key} item")
                            except Exception:
                                payload = None
                            if isinstance(payload, dict):
                                items.append(payload)
                            index = end + 1
                            break
                else:
                    break
            elif char == "]":
                break
            index += 1
        return items

    def _extract_json_string_list(self, text: str, key: str) -> list[str]:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*\[(.*?)\]', text, flags=re.DOTALL)
        if not match:
            return []
        values: list[str] = []
        for item in re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1)):
            try:
                values.append(json.loads(f'"{item}"'))
            except Exception:
                values.append(item)
        return [value for value in values if str(value).strip()]

    def _salvage_qa_payload(self, raw: str) -> dict | None:
        text = strip_code_fences(raw)
        if not text:
            return None

        issues = self._extract_json_array_objects(text, "issues")
        errors = self._extract_json_array_objects(text, "errors")
        if not issues and not errors:
            return None

        payload: dict[str, object] = {
            "issues": issues,
            "errors": errors,
            "suggestions": self._extract_json_string_list(text, "suggestions"),
        }

        score_match = re.search(r'"overall_score"\s*:\s*(-?\d+)', text)
        if score_match:
            payload["overall_score"] = int(score_match.group(1))

        word_count_match = re.search(r'"word_count_ok"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
        if word_count_match:
            payload["word_count_ok"] = word_count_match.group(1).lower() == "true"

        return self._parse_qa_payload(json.dumps(payload, ensure_ascii=False))

    def _is_low_fidelity_salvage(self, payload: dict | None, raw: str) -> bool:
        if not isinstance(payload, dict):
            return True
        issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
        errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
        suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
        raw_text = strip_code_fences(str(raw or "")).strip()
        if not issues and not errors:
            return True
        if len(issues) + len(errors) == 1:
            if not suggestions and "overall_score" not in str(raw_text):
                return True
        if self._looks_like_analysis_only_output(raw_text):
            return True
        if raw_text.count("\n") >= 8 and len(issues) + len(errors) <= 1 and not suggestions:
            return True
        return False

    def _build_normalization_prompt(self, invalid_output: str) -> str:
        return (
            "Convert the following QA notes into one valid JSON object only.\n"
            "Do not add any analysis outside JSON.\n"
            "The first non-whitespace character must be `{` and the last character must be `}`.\n"
            "If the source is truncated, keep only complete issues you can recover faithfully.\n"
            "Do not invent facts not present in the source text.\n"
            "If the source contains prose analysis instead of JSON, extract up to 6 strongest issues into the required schema.\n"
            "Use this exact shape:\n"
            "{\n"
            '  "issues": [{"type": "", "severity": "", "title": "", "description": "", "location": {"script_section": "", "line_range": []}, "suggestion": "", "fix_mode": "auto"}],\n'
            '  "errors": [],\n'
            '  "word_count_ok": true,\n'
            '  "overall_score": 7,\n'
            '  "suggestions": [""]\n'
            "}\n\n"
            "Source QA notes:\n"
            f"{invalid_output[:5000]}"
        )

    def _build_compact_fallback_prompt(self, prompt: str) -> str:
        return (
            "Return one JSON object only. No markdown fences. No analysis.\n"
            "The first non-whitespace character of your response must be `{` and the last character must be `}`.\n"
            "Use this exact shape:\n"
            "{\n"
            '  "issues": [\n'
            "    {\n"
            '      "type": "continuity",\n'
            '      "severity": "high",\n'
            '      "title": "short issue title",\n'
            '      "description": "specific problem",\n'
            '      "location": {"script_section": "scene label", "line_range": []},\n'
            '      "suggestion": "specific fix suggestion",\n'
            '      "fix_mode": "auto"\n'
            "    }\n"
            "  ],\n"
            '  "errors": [],\n'
            '  "word_count_ok": true,\n'
            '  "overall_score": 7,\n'
            '  "suggestions": ["summary suggestion"]\n'
            "}\n\n"
            "Rules:\n"
            "- Maximum 6 issues.\n"
            "- If an issue is about character portrait drift, mark it clearly.\n"
            "- If an issue is about evidence only existing in dialogue, mark it clearly.\n"
            "- Every issue must include a concrete script section label.\n"
            "- If there are fewer than 6 meaningful issues, return fewer. Never pad with fake issues.\n"
            "- Output valid JSON only.\n\n"
            f"{prompt}"
        )

    def _looks_like_analysis_only_output(self, raw: str) -> bool:
        text = strip_code_fences(str(raw or "")).strip()
        if not text:
            return True
        if "{" in text and '"issues"' in text and '"errors"' in text:
            return False
        opening = "\n".join(text.splitlines()[:18]).lower()
        marker_hits = sum(1 for marker in self.ANALYSIS_MARKERS if marker.lower() in opening)
        return marker_hits >= 2

    def _call_structured_qa(self, prompt: str, system: str) -> dict:
        previous_output = ""
        last_error: Exception | None = None
        for attempt in range(2):
            retry_notice = ""
            if attempt > 0:
                retry_notice = (
                    "## Retry Notice\n"
                    "Your previous response did not satisfy the JSON contract.\n"
                    "Return valid JSON only. Do not include analysis outside JSON.\n\n"
                )
            raw = call_llm(
                f"{retry_notice}{prompt}",
                system=system,
                estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT,
                temperature=0.1,
            )
            try:
                return self._parse_qa_payload(raw)
            except Exception as exc:
                previous_output = str(raw or "")
                write_debug_output(self._debug_output_path(attempt + 1), previous_output)
                last_error = exc
                logger.warning("QA output invalid on attempt %s: %s", attempt + 1, exc)
        logger.warning("QA structured path failed, entering compact JSON fallback: %s", last_error)
        raw = call_llm(
            self._build_compact_fallback_prompt(prompt),
            system=system,
            estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT,
            temperature=0.1,
        )
        write_debug_output(self._debug_output_path(3), raw)
        try:
            return self._parse_qa_payload(raw)
        except Exception as exc:
            logger.warning("QA compact fallback invalid, attempting salvage: %s", exc)
            salvaged = self._salvage_qa_payload(raw)
            if salvaged and not self._is_low_fidelity_salvage(salvaged, raw):
                return salvaged

            if self._looks_like_analysis_only_output(raw):
                raw = call_llm(
                    self._build_compact_fallback_prompt(prompt),
                    system=system,
                    estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT,
                    temperature=0.0,
                )
                write_debug_output(self._debug_output_path(4), raw)
                try:
                    return self._parse_qa_payload(raw)
                except Exception as retry_exc:
                    salvaged = self._salvage_qa_payload(raw)
                    if salvaged and not self._is_low_fidelity_salvage(salvaged, raw):
                        return salvaged
                    raise retry_exc from exc

            normalized_raw = call_llm(
                self._build_normalization_prompt(str(raw or "")),
                system=system,
                estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT,
                temperature=0.0,
            )
            write_debug_output(self._debug_output_path(5), normalized_raw)
            try:
                return self._parse_qa_payload(normalized_raw)
            except Exception as normalize_exc:
                salvaged = self._salvage_qa_payload(normalized_raw)
                if salvaged:
                    return salvaged
                raise normalize_exc from exc

    def _debug_output_path(self, attempt: int):
        return config.output_path(
            self._book_title,
            "qa",
            f"episode_{self._episode:02d}_qa_invalid_attempt_{attempt}.txt",
        )

    def _qa_output_path(self):
        return config.output_path(self._book_title, "qa", f"episode_{self._episode:02d}_qa.json")

    def run(self, episode: int) -> dict:
        try:
            with self.session() as session:
                book = session.get(Book, self.book_id)
                if not book:
                    raise ValueError(f"Book {self.book_id} not found")
                self._book_title = book.title
                self._episode = episode

                bible_entry = session.query(BookBible).filter(
                    BookBible.book_id == self.book_id
                ).first()
                script = session.query(Script).filter(
                    Script.book_id == self.book_id,
                    Script.episode == episode,
                ).first()
                if not script:
                    raise ValueError(f"Script for episode {episode} not found. Run 'script' first.")

                bible_chars = self._build_character_bible_excerpt(bible_entry.content if bible_entry else "")
                portrait_info = self._build_portrait_info(session)
                prompt = self._build_prompt(
                    episode=episode,
                    bible_chars=bible_chars,
                    portrait_info=portrait_info,
                    script_content=script.content or "",
                )
                system = "你是短剧剧本质检编辑。必须遵守 Production Skill 约束并只输出合法 JSON。"
                result = self._call_structured_qa(prompt, system)
                error_count = len(_qa_issue_items(result))

                session.add(
                    QAResult(
                        book_id=self.book_id,
                        episode=episode,
                        result=json.dumps(result, ensure_ascii=False, indent=2),
                        error_count=error_count,
                    )
                )
                session.commit()

                qa_path = self._qa_output_path()
                qa_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            return result
        except Exception as exc:
            logger.error("QA failed for book %s episode %s: %s", self.book_id, episode, exc)
            raise

    def generate_report(self) -> str:
        try:
            with self.session() as session:
                book = session.get(Book, self.book_id)
                if not book:
                    raise ValueError(f"Book {self.book_id} not found")

                results = session.query(QAResult).filter(
                    QAResult.book_id == self.book_id
                ).order_by(QAResult.episode).all()

                lines = [f"# 质检报告 - {book.title}\n"]
                total_errors = 0
                for row in results:
                    data = safe_json_loads(row.result, {})
                    score = data.get("overall_score", "?")
                    lines.append(f"\n## 第{row.episode}集 (得分: {score})")
                    issue_items = _qa_issue_items(data)
                    if issue_items:
                        for issue in issue_items:
                            severity = issue.get("severity", "")
                            desc = issue.get("description", "")
                            lines.append(f"- [{severity}] {desc}")
                            total_errors += 1
                    else:
                        lines.append("- 无问题")

                lines.append(f"\n---\n总计发现 {total_errors} 个问题")

                output = config.output_path(book.title, "qa", "质检报告.md")
                output.write_text("\n".join(lines), encoding="utf-8")
            return str(output)
        except Exception as exc:
            logger.error("QA report generation failed for book %s: %s", self.book_id, exc)
            raise
