"""Portrait QA — 人物画像质检模块。

在 portrait 生成后运行，检测：
1. 疑似重复角色（外貌相似 + 章节互补）
2. 性别冲突（同一 canonical 下 gender 不一致）
3. 孤立 profile（与其他角色无关系链接）
4. 性别缺失（gender 为空或"人物"）
5. 章节互补（A 不出场时 B 出场，疑似同一人）
"""
import json
import logging
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from models import Chapter, CharacterProfile, CharacterStage
from core import safe_json_loads

logger = logging.getLogger(__name__)


@dataclass
class CharacterIssue:
    issue_type: str  # "duplicate_suspect", "gender_conflict", "orphan_profile", "missing_gender", "chapter_complement"
    severity: str  # "high", "medium", "low"
    characters: list[str] = field(default_factory=list)
    description: str = ""
    suggestion: str = ""  # "merge", "confirm_gender", "delete", "specify_gender"
    auto_resolvable: bool = False
    evidence: dict = field(default_factory=dict)


@dataclass
class MergeCandidate:
    char_a: str
    char_b: str
    confidence: str  # "high", "medium", "low"
    reason: str
    shared_fragments: list[str] = field(default_factory=list)
    complementary_chapters: list[int] = field(default_factory=list)


@dataclass
class PortraitQAReport:
    book_id: int
    total_characters: int = 0
    issues: list = field(default_factory=list)
    merge_candidates: list = field(default_factory=list)
    gender_conflicts: list = field(default_factory=list)

    def to_dict(self):
        return {
            "book_id": self.book_id,
            "total_characters": self.total_characters,
            "issues": [asdict(i) for i in self.issues],
            "merge_candidates": [asdict(m) for m in self.merge_candidates],
            "gender_conflicts": [asdict(g) for g in self.gender_conflicts],
        }


def run_portrait_qa(book_id: int, session) -> PortraitQAReport:
    """运行人物画像质检。"""
    report = PortraitQAReport(book_id=book_id)

    profiles = session.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id
    ).all()
    report.total_characters = len(profiles)

    if len(profiles) <= 1:
        return report

    # 收集所有章节数据
    chapters = session.query(Chapter).filter(
        Chapter.book_id == book_id
    ).order_by(Chapter.seq).all()

    char_chapters = {}  # {name: set(ch_seq)}
    char_fragments = {}  # {name: [fragment_str]}
    char_relationships = {}  # {name: {rel_name: desc}}

    for ch in chapters:
        if ch.status != "analyzed":
            continue
        ch_seq = ch.seq
        try:
            chars = safe_json_loads(ch.character_table, [])
            for c in chars:
                name = c.get("name", "")
                if name:
                    char_chapters.setdefault(name, set()).add(ch_seq)
                    rels = c.get("relationships", {})
                    if rels:
                        char_relationships.setdefault(name, {}).update(rels)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            frags = safe_json_loads(ch.appearance_fragments, {})
            for fname, sentences in frags.items():
                char_fragments.setdefault(fname, []).extend(sentences)
        except (json.JSONDecodeError, TypeError):
            pass

    profile_map = {p.name: p for p in profiles}
    all_names = list(profile_map.keys())

    # 1. 性别缺失检测
    for p in profiles:
        if not p.gender or p.gender in ("人物", "未识别", ""):
            report.issues.append(CharacterIssue(
                issue_type="missing_gender",
                severity="medium",
                characters=[p.name],
                description=f"角色「{p.name}」性别未明确",
                suggestion="specify_gender",
            ))

    # 2. 孤立 profile 检测
    for p in profiles:
        rels = char_relationships.get(p.name, {})
        chapters_appeared = char_chapters.get(p.name, set())
        frags = char_fragments.get(p.name, [])

        if not rels and len(chapters_appeared) <= 1 and not frags:
            report.issues.append(CharacterIssue(
                issue_type="orphan_profile",
                severity="low",
                characters=[p.name],
                description=f"角色「{p.name}」仅出场1章、无关系链接、无外貌描述，疑似碎片角色",
                suggestion="delete",
                evidence={"chapters": sorted(chapters_appeared), "fragments_count": len(frags)},
            ))

    # 3. 疑似重复角色检测（外貌相似度 + 章节互补）
    for i, name_a in enumerate(all_names):
        frags_a = char_fragments.get(name_a, [])
        chs_a = char_chapters.get(name_a, set())
        p_a = profile_map[name_a]

        for name_b in all_names[i + 1:]:
            frags_b = char_fragments.get(name_b, [])
            chs_b = char_chapters.get(name_b, set())
            p_b = profile_map[name_b]

            # 章节重叠检测
            overlap = chs_a & chs_b
            no_overlap = len(overlap) == 0

            # 外貌相似度
            frag_similarity = _compute_fragment_similarity(frags_a, frags_b)
            alias_match = _has_alias_link(p_a, name_a, p_b, name_b)

            # 性别一致性
            gender_conflict = False
            if p_a.gender and p_b.gender and p_a.gender != "人物" and p_b.gender != "人物":
                if p_a.gender != p_b.gender:
                    gender_conflict = True

            # 判断是否疑似重复
            confidence = "low"
            reason_parts = []

            if frag_similarity > 0.6:
                confidence = "high" if no_overlap else "medium"
                reason_parts.append(f"外貌相似度{frag_similarity:.0%}")
            elif frag_similarity > 0.3:
                confidence = "medium" if no_overlap else "low"
                reason_parts.append(f"外貌部分相似{frag_similarity:.0%}")

            if alias_match:
                reason_parts.append("别名互相指向")
                if confidence in ("low", "medium"):
                    confidence = "high" if no_overlap else "medium"

            # 身份相似度
            id_sim = 0.0
            if p_a.identity and p_b.identity:
                id_sim = SequenceMatcher(None, p_a.identity, p_b.identity).ratio()
                if id_sim > 0.5:
                    reason_parts.append(f"身份相似度{id_sim:.0%}")
                    if confidence == "low":
                        confidence = "medium"

            has_strong_identity_evidence = bool(alias_match or frag_similarity > 0.3 or id_sim > 0.65)
            if no_overlap and has_strong_identity_evidence:
                reason_parts.append("章节完全互补（无重叠）")

            if reason_parts and has_strong_identity_evidence and not gender_conflict:
                report.merge_candidates.append(MergeCandidate(
                    char_a=name_a,
                    char_b=name_b,
                    confidence=confidence,
                    reason="；".join(reason_parts),
                    complementary_chapters=sorted((chs_a | chs_b) - overlap),
                ))

                if confidence == "high":
                    report.issues.append(CharacterIssue(
                        issue_type="duplicate_suspect",
                        severity="high",
                        characters=[name_a, name_b],
                        description=f"疑似重复角色：{name_a} ↔ {name_b}",
                        suggestion="merge",
                        auto_resolvable=False,  # 需用户确认
                        evidence={"frag_similarity": frag_similarity, "overlap": sorted(overlap)},
                    ))

            # 性别冲突
            if gender_conflict and has_strong_identity_evidence:
                report.gender_conflicts.append(CharacterIssue(
                    issue_type="gender_conflict",
                    severity="high",
                    characters=[name_a, name_b],
                    description=f"性别冲突：{name_a}({p_a.gender}) ↔ {name_b}({p_b.gender})",
                    suggestion="confirm_gender",
                    evidence={"frag_similarity": frag_similarity, "overlap": sorted(overlap)},
                ))

    # 4. 按 severity 排序
    severity_order = {"high": 0, "medium": 1, "low": 2}
    report.issues.sort(key=lambda x: severity_order.get(x.severity, 99))
    report.merge_candidates.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.confidence, 99))

    logger.info("Portrait QA: %d 个角色, %d 个问题, %d 个合并候选, %d 个性别冲突",
                report.total_characters, len(report.issues),
                len(report.merge_candidates), len(report.gender_conflicts))
    return report


def _compute_fragment_similarity(frags_a: list[str], frags_b: list[str]) -> float:
    """计算两组外貌片段的文本相似度。"""
    if not frags_a or not frags_b:
        return 0.0

    # 合并为单一文本
    text_a = " ".join(frags_a)
    text_b = " ".join(frags_b)

    if not text_a.strip() or not text_b.strip():
        return 0.0

    return SequenceMatcher(None, text_a, text_b).ratio()


def _has_alias_link(profile_a, name_a: str, profile_b, name_b: str) -> bool:
    """Return True only when stored aliases explicitly connect the two names."""
    aliases_a = set(safe_json_loads(profile_a.aliases, [])) if profile_a and profile_a.aliases else set()
    aliases_b = set(safe_json_loads(profile_b.aliases, [])) if profile_b and profile_b.aliases else set()
    return name_b in aliases_a or name_a in aliases_b


def _has_gender_conflict(profile_a, profile_b) -> bool:
    known_unknowns = {"", "人物", "未识别"}
    gender_a = (profile_a.gender or "").strip()
    gender_b = (profile_b.gender or "").strip()
    return gender_a not in known_unknowns and gender_b not in known_unknowns and gender_a != gender_b


def merge_characters(book_id: int, name_a: str, name_b: str, session,
                     canonical_name: str = None) -> dict:
    """合并两个角色。name_a 保留为 canonical，name_b 被合并进来。

    返回合并结果。
    """
    from models import CharacterProfile, CharacterStage, Chapter

    profile_a = session.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id,
        CharacterProfile.name == name_a,
    ).first()
    profile_b = session.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id,
        CharacterProfile.name == name_b,
    ).first()

    if not profile_a or not profile_b:
        return {"error": f"角色不存在: {name_a} or {name_b}"}

    if _has_gender_conflict(profile_a, profile_b):
        return {"error": f"角色性别冲突，需先人工确认: {name_a}({profile_a.gender}) / {name_b}({profile_b.gender})"}

    canonical = canonical_name or name_a

    # 1. 合并 aliases
    aliases_a = safe_json_loads(profile_a.aliases, [])
    aliases_b = safe_json_loads(profile_b.aliases, [])
    all_aliases = list(set(aliases_a + aliases_b + [name_b]))
    if canonical != name_a:
        all_aliases.append(name_a)
    all_aliases = [a for a in all_aliases if a != canonical]
    profile_a.aliases = json.dumps(all_aliases, ensure_ascii=False)

    # 2. 合并 gender（取非空的）
    if not profile_a.gender or profile_a.gender in ("人物", "未识别"):
        if profile_b.gender and profile_b.gender not in ("人物", "未识别"):
            profile_a.gender = profile_b.gender

    # 3. 合并 identity（取更具体的）
    if (not profile_a.identity or "推测" in (profile_a.identity or "")) and profile_b.identity:
        if "推测" not in (profile_b.identity or ""):
            profile_a.identity = profile_b.identity

    # 4. 合并 appearance_fragments（从 chapter 表）
    chapters = session.query(Chapter).filter(Chapter.book_id == book_id).all()
    for ch in chapters:
        try:
            frags = safe_json_loads(ch.appearance_fragments, {})
            if name_b in frags:
                frags.setdefault(name_a, []).extend(frags.pop(name_b))
                ch.appearance_fragments = json.dumps(frags, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

    # 5. 更新 chapter character_table 中的名字
    for ch in chapters:
        try:
            chars = safe_json_loads(ch.character_table, [])
            changed = False
            for c in chars:
                if c.get("name") == name_b:
                    c["name"] = name_a
                    changed = True
            if changed:
                ch.character_table = json.dumps(chars, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

    # 6. 更新 CharacterStage
    stages = session.query(CharacterStage).filter(
        CharacterStage.book_id == book_id,
        CharacterStage.character_name == name_b,
    ).all()
    for st in stages:
        st.character_name = name_a

    # 7. 删除 profile_b
    session.delete(profile_b)
    session.commit()

    logger.info("合并角色: %s ← %s (aliases: %s)", name_a, name_b, all_aliases)
    return {
        "merged_into": name_a,
        "removed": name_b,
        "aliases": all_aliases,
        "gender": profile_a.gender,
        "identity": profile_a.identity,
    }
