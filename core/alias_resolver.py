"""Alias Resolver — 人物别名归并。

从 reader 输出中提取所有角色名和别名，用 LLM 归并为 canonical name。
解决同一个人在不同章节使用不同称呼的问题（如 陈二蛋→二蛋→黑手双城→陈老魔）。
"""
import json
import logging
from collections import defaultdict
from models import Chapter, CharacterProfile, CharacterStage, Book
from core import safe_json_loads
from core.llm import call_llm_json
from core.prompts import load_prompt


logger = logging.getLogger(__name__)


def resolve_aliases(book_id: int, session):
    """主入口：从所有章节中归并别名，将 profile 中的 name 更新为 canonical name。

    流程:
    1. 从 CharacterProfile 表收集所有角色名及其 aliases
    2. 从 bible 提取故事情节摘要
    3. 用 LLM 将同一实体的别名归并到 canonical name
    4. 更新 CharacterProfile.name 和 CharacterStage.character_name
    5. 更新 chapter 表中的角色名

    返回: {canonical_name: [old_name1, old_name2, ...]}
    """
    book = session.get(Book, book_id)
    if not book:
        raise ValueError(f"Book {book_id} not found")

    # Step 1: 收集所有角色名 — 从 chapter 的 raw character_table 收集
    # 这比从 profile 表更准确，因为包含了所有 reader 提取的角色
    chapters_list = session.query(Chapter).filter(
        Chapter.book_id == book_id
    ).order_by(Chapter.seq).all()

    # 从 chapter 表收集所有名字（raw，未经归并）
    raw_chapter_names = {}  # {name: [ch_seqs]}
    for ch in chapters_list:
        if ch.status != "analyzed":
            continue
        try:
            chars = safe_json_loads(ch.character_table, [])
            for c in chars:
                name = c.get("name", "")
                if name:
                    raw_chapter_names.setdefault(name, []).append(ch.seq)
        except (json.JSONDecodeError, TypeError):
            pass

    # 同时从 profile 表获取 alias 信息
    profiles = session.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id
    ).all()
    name_map = {p.name: p for p in profiles}

    # 合并两源
    all_names = list(set(list(raw_chapter_names.keys()) + list(name_map.keys())))
    all_names.sort()
    logger.info("从 chapter 收集 %d 个名字, profile 表 %d 个", len(raw_chapter_names), len(profiles))
    logger.info("合并后共 %d 个唯一角色名", len(all_names))

    # 构建 name_chapters（优先用 raw_chapter_names）
    name_chapters = dict(raw_chapter_names)
    for name in name_map:
        if name not in name_chapters:
            # 从 profile 找对应章节（如果 profile 的 alias 中有 chapter 里出现的名字）
            name_chapters[name] = []
            for raw_name, chs in raw_chapter_names.items():
                p = name_map.get(name)
                if p and p.aliases:
                    try:
                        alias_list = safe_json_loads(p.aliases, [])
                        if raw_name in alias_list:
                            name_chapters[name] = sorted(set(name_chapters[name] + chs))
                    except: pass

    if len(all_names) <= 1:
        return {n: [n] for n in all_names}

    # Step 2.5: 从 bible 提取故事概要
    from models import BookBible
    bible = session.query(BookBible).filter(
        BookBible.book_id == book_id
    ).first()
    bible_summary = bible.content[:3000] if bible else "无"

    # Step 2.6: 聚合 appearance_fragments 和 relationships（跨章）
    all_fragments = {}  # {name: [sentence1, sentence2, ...]}
    all_relationships = {}  # {name: {rel_name: desc, ...}}
    for ch in chapters_list:
        if ch.status != "analyzed":
            continue
        try:
            frags = safe_json_loads(ch.appearance_fragments, {})
            for fname, sentences in frags.items():
                all_fragments.setdefault(fname, []).extend(sentences)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            chars = safe_json_loads(ch.character_table, [])
            for c in chars:
                cname = c.get("name", "")
                rels = c.get("relationships", {})
                if cname and rels:
                    all_relationships.setdefault(cname, {}).update(rels)
        except (json.JSONDecodeError, TypeError):
            pass

    # Step 3: 用 LLM 归并
    prompt = _build_prompt(book.title, all_names, name_chapters, name_map,
                           bible_summary, all_fragments, all_relationships)
    try:
        result = call_llm_json(prompt, estimated_tokens=6000)
        if isinstance(result, dict):
            groups = result.get("merged", [])
            pending = result.get("pending_confirm", [])
            gender_conflicts = result.get("gender_conflicts", [])
        else:
            groups = []
            pending = []
            gender_conflicts = []
    except Exception as e:
        logger.error("LLM 解析失败: %s", e)
        # 回退：用 alias 字段中的简单规则做归并
        groups = _fallback_merge(all_names, name_map)
        pending = []
        gender_conflicts = []

    # 处理 pending_confirm：中置信度的也加入合并组
    for item in pending:
        if not isinstance(item, dict):
            continue
        names = item.get("names", [])
        confidence = item.get("confidence", "low")
        if confidence == "medium" and len(names) >= 2:
            groups.append(names)
            logger.info("中置信度合并(需确认): %s — %s", names, item.get("reason", ""))
        else:
            logger.info("低置信度/跳过: %s — %s", names, item.get("reason", ""))

    # 记录性别冲突（不自动合并）
    if gender_conflicts:
        for gc in gender_conflicts:
            if isinstance(gc, dict):
                logger.warning("性别冲突: %s — %s", gc.get("names"), gc.get("reason", ""))

    if not groups:
        logger.info("无归并结果，跳过")
        return {n: [n] for n in all_names}

    # Step 4: 构建规范名称映射
    # {canonical_name: [old_name1, old_name2, ...]}
    canonical_map = {}
    old_to_canonical = {}  # {old_name: canonical_name}
    for group in groups:
        if not group:
            continue
        # 第一个名字作为 canonical
        members = [m.strip() for m in group if m.strip()]
        if not members:
            continue
        canonical = members[0]
        # 如果 canonical 不在原始列表中，跳过该组
        valid_members = [m for m in members if m in name_map]
        if not valid_members:
            continue
        if canonical not in name_map:
            # 如果 canonical 是别名而非现有 profile 名，用第一个有效成员
            canonical = valid_members[0]
        canonical_map[canonical] = valid_members
        for m in valid_members:
            old_to_canonical[m] = canonical

    # 未归并的角色（没出现在任何 group 中的）
    unmerged = [n for n in all_names if n not in old_to_canonical]
    for n in unmerged:
        canonical_map.setdefault(n, []).append(n)
        old_to_canonical[n] = n

    logger.info("归并结果:")
    for canonical, members in sorted(canonical_map.items()):
        if len(members) > 1:
            logger.info("    %s ← %s", canonical, members)

    # Step 5: 更新 DB
    _update_db(book_id, session, canonical_map, old_to_canonical, chapters_list)

    # Step 6: 清理垃圾 profile
    _cleanup_empty_profiles(book_id, session, canonical_map, name_chapters, name_map)

    # Step 7: 保存映射文件
    _save_mapping(book_id, book.title, canonical_map, name_chapters, name_map)

    return canonical_map


def _build_prompt(title: str, all_names: list[str],
                  name_chapters: dict[str, list[int]],
                  name_map: dict[str, object],
                  bible_summary: str = "",
                  all_fragments: dict = None,
                  all_relationships: dict = None) -> str:
    """构建别名归并 prompt。"""
    all_fragments = all_fragments or {}
    all_relationships = all_relationships or {}

    # 对每个角色提取信息
    rows = []
    for name in sorted(all_names):
        chs = name_chapters.get(name, [])
        ch_range = f"第{min(chs)}-{max(chs)}章" if chs else "未知"
        ch_count = len(chs)

        # 从 profile 获取身份
        p = name_map.get(name)
        identity = p.identity if p and p.identity else ""
        gender = p.gender if p and p.gender else ""
        aliases = []
        if p:
            try:
                aliases = safe_json_loads(p.aliases, [])
            except (json.JSONDecodeError, TypeError):
                pass
        alias_str = ", ".join(aliases) if aliases else "无"

        # 提取关键身份线索辅助判断
        context_hints = []
        if p:
            if p.aliases:
                try:
                    parsed = safe_json_loads(p.aliases, [])
                    if parsed:
                        context_hints.append(f"alias={','.join(parsed)}")
                except: pass
        if "推测" in identity or "猜测" in identity:
            context_hints.append("（身份推测中）")

        hint_str = " " + " ".join(context_hints) if context_hints else ""

        # 外貌碎片（关键判断依据）
        fragments = all_fragments.get(name, [])
        frag_lines = ""
        if fragments:
            # 去重 + 限制数量
            seen = set()
            unique_frags = []
            for f in fragments:
                f_clean = f.strip()
                if f_clean and f_clean not in seen:
                    seen.add(f_clean)
                    unique_frags.append(f_clean)
            frag_lines = "\n    ".join(unique_frags[:8])
            frag_lines = f"\n  外貌片段:\n    {frag_lines}"

        # 人物关系（辅助判断）
        rels = all_relationships.get(name, {})
        rel_lines = ""
        if rels:
            rel_parts = [f"{r}: {d}" for r, d in list(rels.items())[:6]]
            rel_lines = f"\n  关系: {'; '.join(rel_parts)}"

        # 性别信息
        gender_str = f"\n  性别: {gender}" if gender and gender != "人物" else "\n  性别: 未明确"

        rows.append(
            f"- {name}: 出场{ch_range} ({ch_count}章), "
            f"identity={identity}{hint_str}, aliases={alias_str}"
            f"{gender_str}{frag_lines}{rel_lines}"
        )

    # 添加跨章线索：检查别名中有其他角色名的角色
    cross_refs = []
    for name1 in all_names:
        p1 = name_map.get(name1)
        if not p1 or not p1.aliases:
            continue
        try:
            a1 = safe_json_loads(p1.aliases, [])
        except:
            a1 = []
        for name2 in all_names:
            if name1 != name2 and name2 in a1:
                cross_refs.append(f"- {name1} 的别名包含 {name2}")
    cross_section = "\n".join(cross_refs) if cross_refs else "无"

    # 角色出场排布分析：连续出场 vs 重叠出场
    overlap_info = _analyze_name_chapter_overlap(name_chapters, all_names, name_map)

    prompt = load_prompt(
        "alias_resolve",
        title=title,
        name_count=len(all_names),
        name_rows="\n".join(rows),
        cross_references=cross_section,
        chapter_context=_get_chapter_context(name_chapters, all_names),
        overlap_analysis=overlap_info,
        bible_summary=bible_summary[:3000] if bible_summary else "无",
    )
    return prompt


def _analyze_name_chapter_overlap(name_chapters: dict, all_names: list[str],
                                   name_map: dict) -> str:
    """分析角色出场时间的重叠关系，辅助归并判断。
    
    如果角色 A 和角色 B 从不同时出现在同一章节，且出场章节有衔接，
    可能是同一角色的不同称呼。
    """
    from models import Book
    # 计算总章节数
    max_ch = 0
    for chs in name_chapters.values():
        if chs:
            max_ch = max(max_ch, max(chs))
    
    lines = []
    names = sorted(all_names)
    for i, n1 in enumerate(names):
        chs1 = set(name_chapters.get(n1, []))
        if not chs1:
            continue
        for j in range(i+1, len(names)):
            n2 = names[j]
            chs2 = set(name_chapters.get(n2, []))
            if not chs2:
                continue
            overlap = chs1 & chs2
            if overlap:
                # 有重叠：大概率不同角色（同一章有两个不同称呼出现？可能但不是绝对）
                if len(overlap) <= 2:
                    lines.append(f"- {n1}与{n2}:【少量重叠】共同出场{len(overlap)}章")
            else:
                # 无重叠：可能的别名关系
                min1, max1 = min(chs1), max(chs1)
                min2, max2 = min(chs2), max(chs2)
                gap = min(min2, max2) - max(max1, min1)
                gap_desc = f"间隔{gap}章" if gap > 0 else "无间隔" if gap == 0 else f"反向{gap}章"
                lines.append(f"- {n1}与{n2}:【无重叠】{gap_desc} (第{min1}-{max1}章 vs 第{min2}-{max2}章)")
    
    return "\n".join(lines)


def _get_chapter_context(name_chapters: dict, all_names: list) -> str:
    """生成章节线索：如果两个角色出现在同一章，可能是同一人。"""
    # 按章节分组
    ch_to_names = {}
    for name, chs in name_chapters.items():
        for ch in chs:
            ch_to_names.setdefault(ch, []).append(name)
    # 找在同一章出现的不同角色名
    lines = []
    for ch in sorted(ch_to_names.keys())[:10]:
        names = ch_to_names[ch]
        if len(names) >= 2:
            lines.append(f"第{ch}章出场角色: {', '.join(names)}")
    return "\n".join(lines)


def _update_db(book_id: int, session, canonical_map: dict,
               old_to_canonical: dict,
               chapters: list[Chapter]):
    """更新数据库中的角色名。"""
    from datetime import datetime

    # 5a. 更新 CharacterProfile.name
    profiles = session.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id
    ).all()

    profile_by_old_name = {p.name: p for p in profiles}

    kept = set()  # 保留的 canonical profile
    for canonical, old_names in canonical_map.items():
        if canonical in profile_by_old_name:
            kept.add(canonical)
            p = profile_by_old_name[canonical]
            # 更新 aliases（包含其他旧名）
            all_aliases = [n for n in old_names if n != canonical]
            existing = safe_json_loads(p.aliases, [])
            for a in existing:
                if a not in all_aliases:
                    all_aliases.append(a)
            p.aliases = json.dumps(all_aliases, ensure_ascii=False)

    # 多余的 profile 标记或者删除（非 canonical 的 profile 名）
    for p in profiles:
        if p.name not in kept:
            logger.info("删除冗余 profile: %s (归并到 %s)", p.name, old_to_canonical.get(p.name, '?'))
            session.delete(p)

    # 5b. 更新 CharacterStage.character_name
    stages = session.query(CharacterStage).filter(
        CharacterStage.book_id == book_id
    ).all()
    for st in stages:
        if st.character_name in old_to_canonical:
            new_name = old_to_canonical[st.character_name]
            if new_name != st.character_name:
                # 检查 canonical 是否已有同名 stage
                existing = session.query(CharacterStage).filter(
                    CharacterStage.book_id == book_id,
                    CharacterStage.character_name == new_name,
                    CharacterStage.chapter_start == st.chapter_start,
                ).first()
                if existing:
                    # merge: 保留已有的，删除当前
                    logger.info("合并 stage: %s→%s (ch.%s)", st.character_name, new_name, st.chapter_start)
                    session.delete(st)
                else:
                    st.character_name = new_name

    # 5c. 更新 chapter 中的角色名（JSON character_table）
    for ch in chapters:
        try:
            chars = safe_json_loads(ch.character_table, [])
            changed = False
            for c in chars:
                old_name = c.get("name", "")
                if old_name in old_to_canonical and old_to_canonical[old_name] != old_name:
                    c["name"] = old_to_canonical[old_name]
                    changed = True
                # 更新 aliases 中的别名
                old_aliases = list(c.get("aliases", []))
                new_aliases = []
                for a in old_aliases:
                    if a in old_to_canonical and old_to_canonical[a] != a:
                        new_aliases.append(old_to_canonical[a])
                    else:
                        new_aliases.append(a)
                if set(new_aliases) != set(old_aliases):
                    c["aliases"] = new_aliases
                    changed = True
            if changed:
                ch.character_table = json.dumps(chars, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

        # 5d. 更新 appearance_fragments 中的旧名
        try:
            frags = safe_json_loads(ch.appearance_fragments, {})
            changed = False
            new_frags = {}
            for old_name, sentences in frags.items():
                canonical = old_to_canonical.get(old_name, old_name)
                if canonical != old_name:
                    changed = True
                    new_frags.setdefault(canonical, []).extend(sentences)
                else:
                    new_frags.setdefault(old_name, []).extend(sentences)
            if changed:
                ch.appearance_fragments = json.dumps(new_frags, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

    session.commit()


def _cleanup_empty_profiles(book_id: int, session,
                      canonical_map: dict,
                      name_chapters: dict[str, list[int]],
                      name_map: dict[str, object]):
    """清理无意义角色 profile：chapter_range 无实际章节、identity 为空、appearance_fragments 完全空。
    
    这些角色通常是 reader 提取时的碎片，没有被其他章节引用。
    """
    from datetime import datetime
    from models import Chapter, CharacterProfile, CharacterStage
    import json

    # 收集 appearance_fragments 中出现的所有名字（这些也是有效的角色引用）
    frag_names = set()
    chapters = session.query(Chapter).filter(
        Chapter.book_id == book_id
    ).all()
    for ch in chapters:
        try:
            frags = safe_json_loads(ch.appearance_fragments, {})
            for name in frags:
                if frags[name]:  # 有实际外貌片段
                    frag_names.add(name)
        except:
            pass

    profiles = session.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id
    ).all()

    for p in profiles:
        # 检查组内的别名来源都有实际章节
        original_names = canonical_map.get(p.name, [p.name])
        has_chapter_data = False
        for name in original_names:
            chs = name_chapters.get(name, [])
            if chs:
                has_chapter_data = True
                break
            # 也检查 appearance_fragments
            if name in frag_names:
                has_chapter_data = True
                break

        if has_chapter_data:
            continue

        # 没有实际章节 — 检查是否有 stage
        stage_count = session.query(CharacterStage).filter(
            CharacterStage.book_id == book_id,
            CharacterStage.character_name == p.name,
        ).count()
        if stage_count > 0:
            continue

        # identity 为空或未知
        identity = (p.identity or "").strip()
        if identity and identity != "未知":
            continue

        # 标记为可清理
        logger.info("清理垃圾 profile: %s (无章节, 无身份, 无 stage)", p.name)
        session.delete(p)

    session.commit()


def _save_mapping(book_id: int, title: str,
                  canonical_map: dict,
                  name_chapters: dict[str, list[int]],
                  name_map: dict[str, object]):
    """保存归并映射到文件（人工审阅用）。"""
    import config
    lines = [f"# {title} - 角色别名归并结果\n"]

    for canonical, old_names in sorted(canonical_map.items()):
        if len(old_names) > 1:
            lines.append(f"\n## {canonical}")
            lines.append(f"规范名: {canonical}")
            lines.append(f"归并来源: {', '.join(old_names)}")
            for name in old_names:
                chs = sorted(name_chapters.get(name, []))
                ch_range = f"第{chs[0]}-{chs[-1]}章" if chs else "未知"
                lines.append(f"  - {name}: 出场{ch_range} ({len(chs)}章)")

    lines.append("\n\n## 未归并（单一名）\n")
    for canonical, old_names in sorted(canonical_map.items()):
        if len(old_names) == 1:
            chs = sorted(name_chapters.get(canonical, []))
            ch_range = f"第{chs[0]}-{chs[-1]}章" if chs else "未知"
            lines.append(f"- {canonical}: 出场{ch_range} ({len(chs)}章)")

    output = config.output_path(title, "analysis", "别名归并.md")
    output.write_text("\n".join(lines), encoding="utf-8")
    logger.info("保存归并结果: %s", output)


def _fallback_merge(all_names: list[str], name_map: dict) -> list[list[str]]:
    """回退策略：基于 alias 字段和命名模式规则做直接归并。
    
    当 LLM 调用失败时，使用规则做归并。
    """
    alias_to_names = {}
    for name in all_names:
        p = name_map.get(name)
        if not p:
            continue
        try:
            aliases = safe_json_loads(p.aliases, [])
        except (json.JSONDecodeError, TypeError):
            aliases = []
        for a in aliases:
            a_lower = a.strip()
            if a_lower and a_lower != name:
                alias_to_names.setdefault(a_lower, set()).add(name)

    used = set()
    groups = []
    group_of = {}

    def _add_to_group(name_a, name_b):
        nonlocal used, groups, group_of
        if name_a == name_b:
            return
        if name_a in group_of and name_b in group_of:
            return
        if name_a in group_of:
            idx = group_of[name_a]
            groups[idx].append(name_b)
            group_of[name_b] = idx
            used.add(name_b)
        elif name_b in group_of:
            idx = group_of[name_b]
            groups[idx].append(name_a)
            group_of[name_a] = idx
            used.add(name_a)
        else:
            idx = len(groups)
            groups.append([name_a, name_b])
            group_of[name_a] = idx
            group_of[name_b] = idx
            used.add(name_a)
            used.add(name_b)

    # 策略1: alias 相互指向
    for name in all_names:
        if name in used:
            continue
        p = name_map.get(name)
        if not p:
            continue
        try:
            aliases = safe_json_loads(p.aliases, [])
        except:
            aliases = []
        for a in aliases:
            a = a.strip()
            if a in all_names and a != name:
                _add_to_group(name, a)
        for other_name in all_names:
            if other_name == name or other_name in used:
                continue
            other_p = name_map.get(other_name)
            if not other_p:
                continue
            try:
                other_aliases = safe_json_loads(other_p.aliases, [])
            except:
                other_aliases = []
            if name in other_aliases:
                _add_to_group(name, other_name)
        if name not in used:
            used.add(name)
            groups.append([name])
            group_of[name] = len(groups) - 1

    # 策略2: *他爹/*他娘 模式 — 陈二蛋他爹 = 我爹 = 老陈
    for name in all_names:
        if "他爹" in name or "他娘" in name:
            for other in all_names:
                if other == name or other in used:
                    continue
                if other in ("我爹", "老陈", "我娘", "母亲"):
                    _add_to_group(name, other)

    # 策略3: 动物别名链 — 小猴子→胖妞
    animal_aliases = {
        "小猴子": ["胖妞"],
        "野猴子": ["小猴子", "胖妞"],
    }
    for src, targets in animal_aliases.items():
        if src in all_names:
            for tgt in targets:
                if tgt in all_names:
                    _add_to_group(src, tgt)

    # 策略4: 跨主角时间线 — 陈二蛋→黑手双城→陈老魔
    for name in all_names:
        p = name_map.get(name)
        if not p:
            continue
        id_str = p.identity or ""
        if "主角" in id_str or "传记" in id_str or "黑手双城" == name:
            # 找其他也包含"主角""传记"的角色
            for other in all_names:
                if other == name or other in used:
                    continue
                op = name_map.get(other)
                if not op:
                    continue
                oid = op.identity or ""
                if "主角" in oid or "传记" in oid:
                    _add_to_group(name, other)

    # 单独角色
    for name in all_names:
        if name not in used:
            used.add(name)
            groups.append([name])

    logger.info("回退归并: %d 组", len(groups))
    for g in groups:
        if len(g) >= 2:
            logger.info("    %s ← %s", g[0], g)
    return groups
