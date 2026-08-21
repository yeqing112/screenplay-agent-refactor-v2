"""Bible QA Agent - 圣经级质量检查，确定性规则 + LLM 创意分析。"""
from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher

import config
from agents.base import BaseAgent
from core import safe_json_loads
from core.llm import call_llm
from core.structured_output import parse_json_object, strip_code_fences
from models import Book, BookBible, Chapter, CharacterProfile

logger = logging.getLogger(__name__)


class BibleQAChecker(BaseAgent):
    """圣经质量检查器 — 在 bible 生成后运行，捕获并可选修复数据问题。"""

    name = "bible_qa"

    SEVERITY_SCORES = {"high": 2.0, "medium": 1.0, "low": 0.35}

    # ── Age/Identity conflict rules ──────────────────────────────
    IDENTITY_AGE_RULES: dict[str, tuple[int, int]] = {
        "学生": (6, 25),
        "老师": (22, 65),
        "教授": (30, 70),
        "医生": (25, 70),
        "护士": (20, 60),
        "婴儿": (0, 2),
        "儿童": (3, 12),
        "少年": (13, 17),
        "老人": (65, 100),
        "总裁": (30, 60),
        "CEO": (30, 60),
        "总裁夫人": (25, 55),
        "军人": (18, 55),
        "警察": (20, 55),
        "法官": (35, 65),
        "律师": (25, 65),
        "演员": (16, 60),
        "歌手": (16, 55),
        "画家": (20, 70),
        "科学家": (25, 70),
        "产品经理": (20, 40),
        "程序员": (20, 45),
        "设计师": (20, 50),
        "实习生": (18, 25),
        "新人": (18, 25),
        "退休": (55, 100),
    }

    MALE_IDENTITIES = {"和尚", "武僧", "方丈", "国王", "王子", "丈夫", "新郎", "父亲", "爷爷", "爸爸"}
    FEMALE_IDENTITIES = {"尼姑", "王后", "公主", "妻子", "新娘", "母亲", "奶奶", "妈妈", "修女", "宫女"}

    def run(self) -> dict:
        """主入口：运行所有检查，返回问题 + 自动修复建议。"""
        try:
            with self.session() as s:
                book = s.get(Book, self.book_id)
                if not book:
                    raise ValueError(f"Book {self.book_id} not found")

                chapters = (
                    s.query(Chapter)
                    .filter(Chapter.book_id == self.book_id)
                    .order_by(Chapter.seq)
                    .all()
                )

                # Collect characters from all chapter analyses
                all_characters: dict[str, dict] = {}
                for ch in chapters:
                    if ch.status != "analyzed":
                        continue
                    for c in safe_json_loads(ch.character_table, []):
                        name = c.get("name", "")
                        if not name:
                            continue
                        if name not in all_characters:
                            all_characters[name] = {
                                "name": name,
                                "aliases": c.get("aliases", []),
                                "identity": c.get("identity", ""),
                                "personality": c.get("personality", ""),
                                "relationships": c.get("relationships", {}),
                                "chapters": [ch.seq],
                            }
                        else:
                            all_characters[name]["chapters"].append(ch.seq)
                            new_id = c.get("identity", "")
                            if new_id and not all_characters[name].get("identity"):
                                all_characters[name]["identity"] = new_id

                # Load portrait data
                portraits: dict[str, CharacterProfile] = {}
                try:
                    for p in s.query(CharacterProfile).filter(
                        CharacterProfile.book_id == self.book_id
                    ).all():
                        portraits[p.name] = p
                except Exception as exc:
                    logger.warning("Failed to load portraits for bible QA: %s", exc)

                # Load bible content
                bible_entry = s.query(BookBible).filter(
                    BookBible.book_id == self.book_id
                ).first()
                bible_content = bible_entry.content if bible_entry else ""

                # ── Run all deterministic checks ──
                issues: list[dict] = []
                auto_fixes: list[dict] = []

                for checker in [
                    self._validate_age_identity_consistency,
                    self._validate_gender_consistency,
                    self._validate_relationship_consistency,
                    self._validate_completeness,
                    self._validate_chapter_continuity,
                    self._detect_duplicate_characters,
                ]:
                    result = checker(all_characters, portraits)
                    issues.extend(result.get("issues", []))
                    auto_fixes.extend(result.get("auto_fixes", []))

                # ── LLM creative check ──
                llm_result = self._llm_creative_check(
                    bible_content, all_characters, portraits
                )
                issues.extend(llm_result.get("issues", []))

                # ── Compute score ──
                overall_score = self._estimate_score(issues)

                # ── Build output ──
                result = {
                    "issues": issues,
                    "overall_score": overall_score,
                    "auto_fixes": auto_fixes,
                    "manual_fixes": [
                        {
                            "issue": i.get("title", ""),
                            "instruction": i.get("suggestion", ""),
                        }
                        for i in issues
                        if i.get("fix_mode") == "manual"
                    ],
                    "character_count": len(all_characters),
                }

                # Save QA result as JSON
                qa_path = config.output_path(book.title, "bible_qa.json")
                qa_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self.log(
                    f"Bible QA completed: {len(issues)} issues, "
                    f"score={overall_score}, {len(auto_fixes)} auto-fixes"
                )

            return result

        except Exception as exc:
            logger.error("Bible QA failed for book %s: %s", self.book_id, exc)
            raise

    # ════════════════════════════════════════════════════════════════
    # Deterministic validators
    # ════════════════════════════════════════════════════════════════

    def _validate_age_identity_consistency(
        self, characters: dict, portraits: dict
    ) -> dict:
        """Check age_range vs identity/occupation conflicts."""
        issues, auto_fixes = [], []

        for name, char in characters.items():
            portrait = portraits.get(name)
            age_range = (portrait.age_range if portrait else "") or ""
            identity = char.get("identity", "")

            if not age_range or not identity:
                continue

            # Parse age from various formats: "25-35岁", "55+", "老年(55+)", "青年(25-35)"
            min_age, max_age = self._parse_age_range(age_range)
            if min_age is None:
                continue

            # Check against identity rules
            for keyword, (rule_min, rule_max) in self.IDENTITY_AGE_RULES.items():
                if keyword in identity:
                    if max_age < rule_min or min_age > rule_max:
                        issue = {
                            "type": "age_identity_conflict",
                            "severity": "high",
                            "title": f"{name}: 年龄 {age_range} 与身份「{identity}」不匹配",
                            "description": (
                                f"角色「{name}」年龄 {age_range}，"
                                f"但身份「{identity}」通常要求 {rule_min}-{rule_max} 岁。"
                            ),
                            "character": name,
                            "location": {"character": name, "field": "age_range"},
                            "suggestion": f"调整年龄范围至 {rule_min}-{rule_max}，或修正身份描述。",
                            "fix_mode": "auto",
                        }
                        issues.append(issue)

                        # Auto-fix: clamp age to valid range
                        fixed_min = max(min_age, rule_min)
                        fixed_max = min(max_age, rule_max)
                        if fixed_min <= fixed_max:
                            auto_fixes.append({
                                "character": name,
                                "field": "age_range",
                                "old_value": age_range,
                                "new_value": f"{fixed_min}-{fixed_max}岁",
                                "reason": f"匹配身份「{identity}」的合理年龄范围",
                            })
                        break

        return {"issues": issues, "auto_fixes": auto_fixes}

    def _validate_gender_consistency(
        self, characters: dict, portraits: dict
    ) -> dict:
        """Check gender vs identity/occupation conflicts."""
        issues, auto_fixes = [], []

        for name, char in characters.items():
            portrait = portraits.get(name)
            gender = (portrait.gender if portrait else "") or ""
            identity = char.get("identity", "")

            if not gender or not identity:
                continue

            gender_lower = gender.strip()
            for male_kw in self.MALE_IDENTITIES:
                if male_kw in identity and gender_lower in ("女", "female", "f", "女性"):
                    issues.append({
                        "type": "gender_identity_conflict",
                        "severity": "high",
                        "title": f"{name}: 性别「{gender}」与身份「{identity}」冲突",
                        "description": (
                            f"角色「{name}」性别为「{gender}」，"
                            f"但身份「{identity}」通常为男性。"
                        ),
                        "character": name,
                        "location": {"character": name, "field": "gender"},
                        "suggestion": "修正性别或身份描述。",
                        "fix_mode": "manual",
                    })
                    break

            for female_kw in self.FEMALE_IDENTITIES:
                if female_kw in identity and gender_lower in ("男", "male", "m", "男性"):
                    issues.append({
                        "type": "gender_identity_conflict",
                        "severity": "high",
                        "title": f"{name}: 性别「{gender}」与身份「{identity}」冲突",
                        "description": (
                            f"角色「{name}」性别为「{gender}」，"
                            f"但身份「{identity}」通常为女性。"
                        ),
                        "character": name,
                        "location": {"character": name, "field": "gender"},
                        "suggestion": "修正性别或身份描述。",
                        "fix_mode": "manual",
                    })
                    break

        return {"issues": issues, "auto_fixes": auto_fixes}

    def _validate_relationship_consistency(
        self, characters: dict, portraits: dict
    ) -> dict:
        """Check bidirectional relationship coherence and parent-child age gaps."""
        issues, auto_fixes = [], []
        processed_pairs: set[tuple[str, str]] = set()
        char_names = set(characters.keys())

        for name, char in characters.items():
            rels = char.get("relationships", {})
            if not isinstance(rels, dict):
                continue

            for rel_target, rel_desc in rels.items():
                if not isinstance(rel_desc, str):
                    continue

                # Skip if rel_target is not an actual character name
                # (e.g., "同事王浩", "与老人关系", "十年前谋杀案")
                if rel_target not in char_names:
                    continue

                # Check bidirectional consistency
                pair = tuple(sorted([name, rel_target]))
                if pair in processed_pairs:
                    continue
                processed_pairs.add(pair)

                target_char = characters.get(rel_target, {})
                target_rels = target_char.get("relationships", {})
                if not isinstance(target_rels, dict):
                    continue

                # Find reverse relationship
                reverse_found = False
                for t_rel, t_desc in target_rels.items():
                    if name in str(t_rel) or name in str(t_desc):
                        reverse_found = True
                        break

                if not reverse_found and rels:
                    issues.append({
                        "type": "relationship_asymmetry",
                        "severity": "low",
                        "title": f"{name} → {rel_target}: 单向关系",
                        "description": (
                            f"「{name}」声明了与「{rel_target}」的关系（{rel_desc}），"
                            f"但「{rel_target}」的角色数据中未找到反向关系。"
                        ),
                        "character": name,
                        "location": {"character": name, "field": "relationships"},
                        "suggestion": f"在「{rel_target}」中补充反向关系描述。",
                        "fix_mode": "auto",
                    })
                    # Auto-fix: generate reverse relationship
                    reverse_map = {
                        "主治医生与病人关系": "病人与主治医生关系",
                        "病人与主治医生关系": "主治医生与病人关系",
                        "姐妹关系": "姐妹关系",
                        "兄弟关系": "兄弟关系",
                        "夫妻关系": "夫妻关系",
                        "朋友关系": "朋友关系",
                        "同事关系": "同事关系",
                        "邻居关系": "邻居关系",
                    }
                    reverse_desc = reverse_map.get(rel_desc, f"{rel_target}与{name}的关系")
                    auto_fixes.append({
                        "character": rel_target,
                        "field": "relationships",
                        "old_value": str(target_rels),
                        "new_value": {name: reverse_desc},
                        "reason": f"补充反向关系以消除不对称",
                    })

            # Parent-child age gap check
            portrait = portraits.get(name)
            if not portrait:
                continue
            ages = re.findall(r"\d+", portrait.age_range or "")
            if len(ages) < 2:
                continue
            char_age_min = int(ages[0])

            for rel_target, rel_desc in rels.items():
                if not any(
                    kw in str(rel_desc)
                    for kw in ("父子", "母子", "父女", "母女", "父母", "孩子", "儿子", "女儿")
                ):
                    continue
                target_portrait = portraits.get(rel_target)
                if not target_portrait:
                    continue
                t_ages = re.findall(r"\d+", target_portrait.age_range or "")
                if len(t_ages) < 2:
                    continue
                target_age_min = int(t_ages[0])
                gap = abs(char_age_min - target_age_min)
                if gap < 15:
                    issues.append({
                        "type": "parent_child_age_gap",
                        "severity": "medium",
                        "title": f"{name}({portrait.age_range}) 与 {rel_target}({target_portrait.age_range}) 年龄差不足",
                        "description": (
                            f"父子/母子关系要求至少 15 岁年龄差，"
                            f"实际差距仅 {gap} 岁。"
                        ),
                        "character": name,
                        "location": {"character": name, "field": "age_range"},
                        "suggestion": "调整年龄以满足亲子关系合理性。",
                        "fix_mode": "manual",
                    })

        return {"issues": issues, "auto_fixes": auto_fixes}

    def _validate_completeness(
        self, characters: dict, portraits: dict
    ) -> dict:
        """Check for missing critical fields."""
        issues, auto_fixes = [], []

        for name, char in characters.items():
            for field in ("identity", "personality"):
                val = char.get(field, "")
                if not val or not str(val).strip():
                    issues.append({
                        "type": "missing_field",
                        "severity": "medium",
                        "title": f"{name}: 缺少「{field}」",
                        "description": f"角色「{name}」的 {field} 字段为空。",
                        "character": name,
                        "location": {"character": name, "field": field},
                        "suggestion": f"补充「{name}」的{field}信息。",
                        "fix_mode": "manual",
                    })

            portrait = portraits.get(name)
            if portrait:
                for field, label in [("gender", "性别"), ("age_range", "年龄范围"), ("role", "角色定位")]:
                    val = getattr(portrait, field, "")
                    if not val or not str(val).strip():
                        issues.append({
                            "type": "missing_portrait_field",
                            "severity": "medium",
                            "title": f"{name}: 画像缺少「{label}」",
                            "description": f"角色「{name}」的画像中 {label} 为空。",
                            "character": name,
                            "location": {"character": name, "field": field},
                            "suggestion": f"补充「{name}」的{label}信息。",
                            "fix_mode": "manual",
                        })

        return {"issues": issues, "auto_fixes": auto_fixes}

    def _validate_chapter_continuity(
        self, characters: dict, portraits: dict
    ) -> dict:
        """Check for characters that appear sporadically with large gaps."""
        issues, auto_fixes = [], []

        for name, char in characters.items():
            chaps = sorted(char.get("chapters", []))
            if len(chaps) < 2:
                continue

            for i in range(1, len(chaps)):
                gap = chaps[i] - chaps[i - 1]
                if gap > 5:
                    issues.append({
                        "type": "chapter_gap",
                        "severity": "low",
                        "title": f"{name}: 第{chaps[i-1]}章~第{chaps[i]}章间断裂",
                        "description": (
                            f"角色「{name}」在第{chaps[i-1]}章出现后，"
                            f"直到第{chaps[i]}章才再次出现，中间 {gap} 章无踪迹。"
                        ),
                        "character": name,
                        "location": {"character": name, "field": "chapters"},
                        "suggestion": "检查角色在中间章节是否有出场遗漏。",
                        "fix_mode": "manual",
                    })

        return {"issues": issues, "auto_fixes": auto_fixes}

    def _detect_duplicate_characters(
        self, characters: dict, portraits: dict
    ) -> dict:
        """Detect potential duplicate characters by name similarity and shared aliases."""
        issues, auto_fixes = [], []
        names = list(characters.keys())
        checked: set[tuple[str, str]] = set()

        for i, n1 in enumerate(names):
            for n2 in names[i + 1:]:
                pair = tuple(sorted([n1, n2]))
                if pair in checked:
                    continue
                checked.add(pair)

                # Exact alias overlap
                a1 = set(characters[n1].get("aliases", []) or [])
                a2 = set(characters[n2].get("aliases", []) or [])
                shared = a1 & a2
                if shared:
                    issues.append({
                        "type": "duplicate_aliases",
                        "severity": "high",
                        "title": f"{n1} 与 {n2} 共享别名「{', '.join(shared)}」",
                        "description": (
                            f"角色「{n1}」和「{n2}」有相同别名，可能是同一角色的重复。"
                        ),
                        "character": f"{n1}, {n2}",
                        "location": {"characters": [n1, n2]},
                        "suggestion": "确认是否为同一角色，如是则合并。",
                        "fix_mode": "manual",
                    })

                # Name similarity > 0.8
                sim = SequenceMatcher(None, n1, n2).ratio()
                if sim > 0.8 and sim < 1.0:
                    issues.append({
                        "type": "similar_names",
                        "severity": "low",
                        "title": f"{n1} 与 {n2} 名字相似（{sim:.0%}）",
                        "description": (
                            f"角色「{n1}」和「{n2}」名字高度相似，"
                            f"可能是拼写变体或重复角色。"
                        ),
                        "character": f"{n1}, {n2}",
                        "location": {"characters": [n1, n2]},
                        "suggestion": "检查是否为同一角色。",
                        "fix_mode": "manual",
                    })

        return {"issues": issues, "auto_fixes": auto_fixes}

    # ════════════════════════════════════════════════════════════════
    # LLM creative quality check
    # ════════════════════════════════════════════════════════════════

    def _llm_creative_check(
        self,
        bible_content: str,
        characters: dict,
        portraits: dict,
    ) -> dict:
        """LLM-based creative quality analysis for the bible."""
        if not bible_content:
            return {"issues": []}

        # Build character summary for context
        char_lines: list[str] = []
        for name, char in list(characters.items())[:30]:
            portrait = portraits.get(name)
            age_str = f", age={portrait.age_range}" if portrait and portrait.age_range else ""
            gender_str = f", gender={portrait.gender}" if portrait and portrait.gender else ""
            char_lines.append(
                f"- {name}: identity={char.get('identity', '?')}{age_str}{gender_str}, "
                f"chapters={char.get('chapters', [])}"
            )

        prompt = (
            "你是小说圣经质量审核专家。请分析以下小说圣经内容，检查创意层面的问题。\n\n"
            "## 审核维度\n"
            "1. **角色扁平化**: 是否有角色只有姓名无实质性格/动机\n"
            "2. **关系网缺失**: 是否有孤立角色（与主线无关联）\n"
            "3. **身份冲突**: 多处提到同一角色身份不一致\n"
            "4. **主题断裂**: 事件之间是否有逻辑断裂\n"
            "5. **伏笔完整性**: 伏笔是否有对应的回收\n\n"
            "## 角色摘要\n"
            + "\n".join(char_lines) + "\n\n"
            "## 圣经内容（节选）\n"
            f"{bible_content[:6000]}\n\n"
            "## 输出格式\n"
            "返回严格 JSON，格式如下：\n"
            "```json\n"
            "{\n"
            '  "issues": [\n'
            "    {\n"
            '      "type": "creative_quality",\n'
            '      "severity": "medium",\n'
            '      "title": "问题标题",\n'
            '      "description": "具体描述",\n'
            '      "character": "涉及角色（可选）",\n'
            '      "location": {"section": "圣经段落"},\n'
            '      "suggestion": "修改建议",\n'
            '      "fix_mode": "manual"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n\n"
            "规则：\n"
            "- 最多返回 5 个问题\n"
            "- 只报告有实际依据的问题，不要臆测\n"
            "- severity 仅用 high/medium/low\n"
            "- 如果没有发现问题，返回 {\"issues\": []}\n"
            "- 输出合法 JSON，不要添加分析文字"
        )

        system = "你是小说圣经质量审核专家。只输出合法 JSON，不要添加分析文字。"
        try:
            raw = call_llm(
                prompt,
                system=system,
                estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT,
                temperature=0.1,
            )
            parsed = parse_json_object(
                strip_code_fences(raw),
                label="bible_qa_llm",
                required_keys={"issues"},
            )
            issues = parsed.get("issues", [])
            if not isinstance(issues, list):
                return {"issues": []}
            for item in issues:
                if isinstance(item, dict) and "fix_mode" not in item:
                    item["fix_mode"] = "manual"
            return {"issues": issues}
        except Exception as exc:
            logger.warning("Bible QA LLM creative check failed: %s", exc)
            return {"issues": []}

    # ════════════════════════════════════════════════════════════════
    # Scoring
    # ════════════════════════════════════════════════════════════════

    def _parse_age_range(self, age_str: str) -> tuple[int | None, int | None]:
        """Parse age range from various formats. Returns (min, max) or (None, None)."""
        if not age_str:
            return None, None

        # Handle "老年(55+)" or "青年(25-35)" format
        m = re.search(r"[(\uff08](\d+)\+?[)）]", age_str)
        if m:
            age = int(m.group(1))
            if "+" in age_str[m.start():m.end() + 5]:
                return age, 100
            m2 = re.search(r"[(\uff08]\d+[-~](\d+)[)）]", age_str)
            if m2:
                return age, int(m2.group(1))
            return age, age + 20

        # Handle "55+" format
        m = re.search(r"(\d+)\+", age_str)
        if m:
            return int(m.group(1)), 100

        # Handle "25-35" or "25~35" format
        m = re.search(r"(\d+)\s*[-~]\s*(\d+)", age_str)
        if m:
            return int(m.group(1)), int(m.group(2))

        # Handle single number
        ages = re.findall(r"\d+", age_str)
        if len(ages) == 1:
            age = int(ages[0])
            return age, age + 20

        return None, None

    def _estimate_score(self, issues: list[dict]) -> int:
        """Penalty-based scoring, same as script QA."""
        penalty = 0.0
        for item in issues:
            severity = str(item.get("severity", "")).strip().lower()
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
