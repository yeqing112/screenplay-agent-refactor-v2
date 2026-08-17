"""Portrait Agent - character portrait generation with fallback support."""
import json
import logging
import re
from pathlib import Path

import config
from models import Book, Chapter, CharacterProfile, CharacterStage, VisualMakeup
from agents.base import BaseAgent
from agents.portrait_base import generate_base_profile
from agents.portrait_stages import generate_stages
from core import safe_json_loads

logger = logging.getLogger(__name__)


def _clean_makeup_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [item.strip() for item in re.split(r"[，,]", text) if item.strip()]
    deduped: list[str] = []
    for part in parts:
        if any(part == existing or part in existing for existing in deduped):
            continue
        deduped = [existing for existing in deduped if existing not in part]
        deduped.append(part)
    return "，".join(deduped)


class PortraitAgent(BaseAgent):
    """Generate base portraits first, then optional stage variants for important characters."""

    name = "portrait"

    def __init__(self, book_id: int):
        super().__init__(book_id)

    def run(self) -> str:
        with self.session() as s:
            book = s.get(Book, self.book_id)
            if not book:
                raise ValueError(f"Book {self.book_id} not found")

            all_fragments, all_characters = self._aggregate(s)

            if not all_characters and not all_fragments:
                raise ValueError(
                    "No character signals found. "
                    "Make sure 'read' was run with the updated prompt."
                )

            logger.info("=== Step 1: base portraits ===")
            profile_targets = all_characters or {
                name: {"name": name, "aliases": [], "identity": "", "personality": "", "relationships": {}, "chapters": []}
                for name in all_fragments.keys()
            }

            for name, char_info in profile_targets.items():
                fragments = all_fragments.get(name, []) or self._build_fallback_fragments(name, char_info)
                generate_base_profile(
                    book_id=self.book_id,
                    session=s,
                    name=name,
                    fragments=fragments,
                    char_info=all_characters.get(name, char_info),
                )
                logger.info("  [base] %s", name)

            logger.info("=== Step 2: stage portraits ===")
            important_chars = {
                name: info
                for name, info in all_characters.items()
                if len(info.get("chapters", [])) >= 5 and len(all_fragments.get(name, [])) >= 3
            }
            logger.info("  important stage targets: %d", len(important_chars))

            for name, char_info in important_chars.items():
                fragments = all_fragments.get(name, [])
                generate_stages(
                    book_id=self.book_id,
                    session=s,
                    name=name,
                    fragments=fragments,
                    char_info=char_info,
                )
                logger.info("  [stage] %s", name)

            self._sync_base_makeups(s, book.title)

            output = self._save_outputs(book.title)
            book.status = "portraited"
            s.commit()

        return str(output)

    def _build_fallback_fragments(self, name: str, char_info: dict) -> list[str]:
        """Synthesize lightweight portrait hints from character-table signals when no appearance fragments exist."""
        fallback_lines: list[str] = []
        identity = str(char_info.get("identity", "") or "").strip()
        personality = str(char_info.get("personality", "") or "").strip()
        aliases = [str(item).strip() for item in (char_info.get("aliases", []) or []) if str(item).strip()]
        relationships = char_info.get("relationships", {}) or {}

        if identity:
            fallback_lines.append(f"{name} 的身份是：{identity}")
        if personality:
            fallback_lines.append(f"{name} 的性格是：{personality}")
        if aliases:
            fallback_lines.append(f"{name} 的别名有：{'、'.join(aliases)}")
        if isinstance(relationships, dict) and relationships:
            relation_bits = [f"{key}:{value}" for key, value in relationships.items() if str(key).strip() and str(value).strip()]
            if relation_bits:
                fallback_lines.append(f"{name} 的关系线索：{'；'.join(relation_bits[:6])}")

        if not fallback_lines:
            fallback_lines.append(f"{name} 是书中角色，需要基于身份和气质生成基础人物画像。")

        return fallback_lines

    def _aggregate(self, session) -> tuple[dict, dict]:
        all_fragments = {}
        all_characters = {}

        chapters = session.query(Chapter).filter(Chapter.book_id == self.book_id).order_by(Chapter.seq).all()

        for ch in chapters:
            try:
                frags = safe_json_loads(ch.appearance_fragments, {})
                for name, sentences in frags.items():
                    if name not in all_fragments:
                        all_fragments[name] = []
                    for sent in sentences:
                        entry = f"[第{ch.seq}章] {sent}"
                        if entry not in all_fragments[name]:
                            all_fragments[name].append(entry)
            except (json.JSONDecodeError, TypeError):
                pass

            try:
                chars = safe_json_loads(ch.character_table, [])
                for c in chars:
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
                            "first_chapter": ch.seq,
                            "chapters": [ch.seq],
                        }
                    else:
                        all_characters[name]["chapters"].append(ch.seq)
                        new_id = c.get("identity", "")
                        if new_id and not all_characters[name].get("identity"):
                            all_characters[name]["identity"] = new_id
            except (json.JSONDecodeError, TypeError):
                pass

        return all_fragments, all_characters

    def _sync_base_makeups(self, session, book_title: str) -> None:
        """Expose base portrait profiles inside the visual asset center."""
        profiles = (
            session.query(CharacterProfile)
            .filter(CharacterProfile.book_id == self.book_id)
            .order_by(CharacterProfile.name.asc())
            .all()
        )
        if not profiles:
            return

        for profile in profiles:
            existing = (
                session.query(VisualMakeup)
                .filter(
                    VisualMakeup.book_id == self.book_id,
                    VisualMakeup.character_name == profile.name,
                    VisualMakeup.stage_name == "base_identity",
                )
                .first()
            )
            payload = {
                "book_title": book_title,
                "episode": 1,
                "character_name": profile.name,
                "stage_name": "base_identity",
                "refined_outfit": profile.signature_outfit or "",
                "refined_accessories": profile.accessories or "",
                "makeup_spec": _clean_makeup_text(profile.facial_features or profile.skin_tone or ""),
                "hair_style": getattr(profile, "hairstyle", "") or "",
                "expression_mood": profile.temperament or profile.personality or "自然克制",
                "visual_prompt_en": profile.visual_prompt_en or "",
                "visual_prompt_zh": profile.visual_prompt_zh or "",
                "core_prompt_en": profile.core_prompt_en or profile.visual_prompt_en or "",
                "core_prompt_zh": profile.core_prompt_zh or profile.visual_prompt_zh or "",
                "outfit_prompt_en": profile.outfit_prompt_en or "",
                "outfit_prompt_zh": profile.outfit_prompt_zh or "",
                "scene_prompt_en": profile.scene_prompt_en or "",
                "scene_prompt_zh": profile.scene_prompt_zh or "",
                "consistency_notes": "严格继承基础定妆的面部一致性、发型一致性、体型一致性和气质一致性。",
                "meta_info": json.dumps(
                    {
                        "scope": "base_identity",
                        "template_version": "portrait_base_sheet_v1",
                        "prompt_source": "portrait/base_profile",
                        "character_profile_id": profile.id,
                    },
                    ensure_ascii=False,
                ),
                "shot_ids": "[]",
            }
            if existing:
                for key, value in payload.items():
                    setattr(existing, key, value)
            else:
                session.add(VisualMakeup(book_id=self.book_id, **payload))

        session.flush()

    def _save_outputs(self, title: str) -> Path:
        book_title = ""
        with self.session() as s:
            book = s.get(Book, self.book_id)
            book_title = book.title
            profiles = s.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).all()
            stages = (
                s.query(CharacterStage)
                .filter(CharacterStage.book_id == self.book_id)
                .order_by(CharacterStage.character_name, CharacterStage.chapter_start)
                .all()
            )

            data = {
                "profiles": [
                    {
                        "name": p.name,
                        "gender": p.gender,
                        "identity": p.identity,
                        "vibe": p.vibe,
                        "visual_prompt_en": p.visual_prompt_en,
                        "visual_prompt_zh": p.visual_prompt_zh,
                        "core_prompt_en": p.core_prompt_en,
                        "core_prompt_zh": p.core_prompt_zh,
                        "outfit_prompt_en": p.outfit_prompt_en,
                        "outfit_prompt_zh": p.outfit_prompt_zh,
                        "scene_prompt_en": p.scene_prompt_en,
                        "scene_prompt_zh": p.scene_prompt_zh,
                    }
                    for p in profiles
                ],
                "stages": [
                    {
                        "character": st.character_name,
                        "stage": st.stage_name,
                        "chapters": f"{st.chapter_start}-{st.chapter_end}",
                        "identity": st.identity,
                        "age": st.age_description,
                        "vibe": st.vibe,
                        "outfit": st.signature_outfit,
                        "visual_prompt_en": st.visual_prompt_en,
                        "visual_prompt_zh": st.visual_prompt_zh,
                        "core_prompt_en": st.core_prompt_en,
                        "core_prompt_zh": st.core_prompt_zh,
                        "outfit_prompt_en": st.outfit_prompt_en,
                        "outfit_prompt_zh": st.outfit_prompt_zh,
                        "scene_prompt_en": st.scene_prompt_en,
                        "scene_prompt_zh": st.scene_prompt_zh,
                    }
                    for st in stages
                ],
            }
            json_path = config.output_path(book_title, "portraits", "角色画像.json")
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            md_lines = [f"# {title} - 人物画像\n", "\n## 一、基础画像\n"]
            for p in profiles:
                md_lines.append(f"\n### {p.name}\n")
                md_lines.append(f"**性别：** {p.gender} | **身份：** {p.identity}")
                md_lines.append(f"**脸型：** {p.face_shape}")
                md_lines.append(f"**五官：** {p.facial_features}")
                md_lines.append(f"**体型：** {p.body_type}")
                md_lines.append(f"**穿着：** {p.signature_outfit}")
                md_lines.append(f"**气质：** {p.temperament}")
                md_lines.append(f"**氛围：** {p.vibe}")

            md_lines.append("\n\n## 二、阶段化画像\n")
            current_char = None
            for st in stages:
                if st.character_name != current_char:
                    current_char = st.character_name
                    md_lines.append(f"\n### {current_char}\n")
                md_lines.append(f"\n#### {st.stage_name}（第{st.chapter_start}-{st.chapter_end}章）\n")
                md_lines.append(f"**时间线：** {st.timeline}")
                md_lines.append(f"**身份：** {st.identity}")
                md_lines.append(f"**年龄：** {st.age_description}")
                md_lines.append(f"**穿着：** {st.signature_outfit}")
                md_lines.append(f"**气质：** {st.temperament}")
                md_lines.append(f"**氛围：** {st.vibe}")
                md_lines.append(f"\n**EN Prompt:**\n```\n{st.visual_prompt_en}\n```")
                md_lines.append(f"\n**ZH Prompt:**\n```\n{st.visual_prompt_zh}\n```")

            md_path = config.output_path(book_title, "portraits", "角色画像.md")
            md_path.write_text("\n".join(md_lines), encoding="utf-8")

            prompts_lines = []
            for st in stages:
                prompts_lines.append(
                    f"=== {st.character_name} - {st.stage_name} (Ch.{st.chapter_start}-{st.chapter_end}) ==="
                )
                prompts_lines.append(f"[EN] {st.visual_prompt_en}")
                prompts_lines.append(f"[ZH] {st.visual_prompt_zh}")
                if st.core_prompt_en:
                    prompts_lines.append(f"[CORE EN] {st.core_prompt_en}")
                    prompts_lines.append(f"[CORE ZH] {st.core_prompt_zh}")
                    prompts_lines.append(f"[OUTFIT EN] {st.outfit_prompt_en}")
                    prompts_lines.append(f"[OUTFIT ZH] {st.outfit_prompt_zh}")
                    prompts_lines.append(f"[SCENE EN] {st.scene_prompt_en}")
                    prompts_lines.append(f"[SCENE ZH] {st.scene_prompt_zh}")
                prompts_lines.append("")

            prompts_path = config.output_path(book_title, "portraits", "生图提示词.txt")
            prompts_path.write_text("\n".join(prompts_lines), encoding="utf-8")

        logger.info("  - %s/portraits/ (JSON+MD+TXT)", config.sanitize_filename(book_title))
        return md_path
