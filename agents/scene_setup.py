"""Scene Setup Agent — 视觉统筹。包含四个子模块。

8a. era_scan      — 扫描时代规范
8b. props         — 提取道具并生成视觉提示词（按集）
8c. locations     — 提取场景并生成视觉提示词（按集）
8d. makeup        — 精调人物定妆照提示词（按集）
"""
import json
import re
from pathlib import Path

import config
from models import Book, BookBible, Script, CharacterProfile, CharacterStage
from models import VisualEraSpec, VisualProp, VisualLocation, VisualMakeup
from models.visual import VisualProp, VisualLocation, VisualMakeup
from genres import get_genre
from core.llm import call_llm, call_llm_json
from core.prompts import load_prompt
from core import safe_json_loads
from agents.base import BaseAgent
from agents.portrait_base import (
    compile_character_sheet_prompts,
    canonicalize_character_prompt_inputs,
    canonicalize_variant_prompt_inputs,
)


def _force_string(d: dict, field: str, default=""):
    """确保字段为字符串。"""
    v = d.get(field, default)
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False)
    if not isinstance(v, str):
        return str(v)
    return v


def _first_non_empty(*values):
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() not in {"未知", "无描述", "无"}:
            return value.strip()
    return ""


def _format_makeup_scope_label(scope: str) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized == "base_identity":
        return "基础定妆"
    if normalized == "episode_default":
        return "分集默认"
    if normalized == "shot_variant":
        return "分镜精调"
    return str(scope or "").strip()


def _format_makeup_stage_label(stage_name: str, scope: str, episode: int | None = None) -> str:
    cleaned = str(stage_name or "").strip()
    normalized = cleaned.lower()
    normalized_scope = str(scope or "").strip().lower()

    if normalized == "base_identity" or normalized_scope == "base_identity":
        return "基础身份阶段"

    episode_match = re.match(r"^episode_(\d+)_default$", normalized)
    if episode_match:
        return f"第{episode_match.group(1)}集默认造型"

    shot_match = re.match(r"^shot_(\d+)_(.+)$", cleaned, flags=re.IGNORECASE)
    if shot_match:
        return f"镜头 {shot_match.group(1)} · {shot_match.group(2).replace('_', ' ')}"

    if normalized_scope == "episode_default" and episode:
        return f"第{int(episode)}集默认造型"

    return cleaned


class SceneSetupAgent(BaseAgent):
    """视觉统筹 Agent — 时代规范 + 道具 + 场景 + 定妆照精调。"""

    name = "scene_setup"

    def __init__(self, book_id: int, genre: str = "short_drama"):
        super().__init__(book_id)
        self.genre = get_genre(genre)

    # ============================================================
    # 8a. Era Scan
    # ============================================================
    def run_era_scan(self):
        """扫描时代规范并存入 DB。"""
        with self.session() as s:
            book = s.get(Book, self.book_id)
            bible = s.query(BookBible).filter(
                BookBible.book_id == self.book_id
            ).first()
            if not bible:
                raise ValueError("Run 'bible' first.")

            # 从 bible 和 chapter 中提取时间线信息
            timeline_text = self._extract_timeline(s)

            prompt = load_prompt(
                "scene/era_scan",
                timeline_text=timeline_text[:config.TIMELINE_EXCERPT_CHARS],
                bible_excerpt=bible.content[:config.BIBLE_EXCERPT_CHARS],
                genre_name=self.genre.name,
                genre_desc=self.genre.description,
                genre_rules=self._get_genre_rules(),
            )

            result = call_llm_json(prompt, estimated_tokens=config.ESTIMATED_TOKENS_CHAPTER)

            # 确保 time_periods 和 raw_periods 为 JSON 字符串
            for field in ["time_periods", "raw_periods"]:
                v = result.get(field, [])
                if isinstance(v, list):
                    result[field] = json.dumps(v, ensure_ascii=False)

            existing = s.query(VisualEraSpec).filter(
                VisualEraSpec.book_id == self.book_id
            ).first()

            if existing:
                existing.timeline_start = result.get("timeline_start", existing.timeline_start)
                existing.timeline_end = result.get("timeline_end", existing.timeline_end)
                existing.time_periods = result.get("time_periods", existing.time_periods)
                existing.clothing_spec = result.get("clothing_spec", existing.clothing_spec)
                existing.color_palette = result.get("color_palette", existing.color_palette)
                existing.architecture_spec = result.get("architecture_spec", existing.architecture_spec)
                existing.environment_spec = result.get("environment_spec", existing.environment_spec)
                existing.prop_spec = result.get("prop_spec", existing.prop_spec)
                existing.color_curve = result.get("color_curve", existing.color_curve)
                existing.genre_adapt_rules = result.get("genre_adapt_rules", existing.genre_adapt_rules)
                from datetime import datetime
                existing.updated_at = datetime.utcnow()
            else:
                s.add(VisualEraSpec(
                    book_id=self.book_id,
                    timeline_start=result.get("timeline_start", ""),
                    timeline_end=result.get("timeline_end", ""),
                    time_periods=result.get("time_periods", "[]"),
                    clothing_spec=result.get("clothing_spec", ""),
                    color_palette=result.get("color_palette", ""),
                    architecture_spec=result.get("architecture_spec", ""),
                    environment_spec=result.get("environment_spec", ""),
                    prop_spec=result.get("prop_spec", ""),
                    color_curve=result.get("color_curve", ""),
                    genre_adapt_rules=result.get("genre_adapt_rules", ""),
                    raw_periods=result.get("raw_periods", "[]"),
                ))
            s.commit()

        self.log(f"era_scan completed")
        return True

    def _get_genre_rules(self):
        """获取赛道规则文件内容。"""
        prompts_dir = Path(__file__).parent.parent / "prompts" / "genres"
        # 尝试规则文件: {genre_name}_rules.txt
        rules_path = prompts_dir / f"{self.genre.name}_rules.txt"
        if rules_path.exists():
            return rules_path.read_text(encoding="utf-8")[:config.RULES_EXCERPT_CHARS]
        # 回退：尝试任何包含 "rules" 的文件
        for f in prompts_dir.glob(f"{self.genre.name}*rules*"):
            return f.read_text(encoding="utf-8")[:config.RULES_EXCERPT_CHARS]
        return ""

    def _extract_timeline(self, session):
        """从所有章节分析中提取时间线信息。"""
        from models import Chapter
        chapters = session.query(Chapter).filter(
            Chapter.book_id == self.book_id
        ).order_by(Chapter.seq).limit(10).all()
        lines = []
        for ch in chapters:
            summary = ch.summary or ""
            events = ch.events or "[]"
            lines.append(f"第{ch.seq}章: {summary[:200]}")
        for ch in chapters:
            scenes = ch.scenes or "[]"
            try:
                scenes_list = safe_json_loads(scenes, [])
                for sc in scenes_list:
                    if isinstance(sc, dict):
                        loc = sc.get("location", "")
                        if loc:
                            lines.append(f"  场景: {loc}")
            except (json.JSONDecodeError, TypeError):
                pass
        return "\n".join(lines[:100])

    # ============================================================
    # 8b. Props
    # ============================================================
    def run_props(self, episode: int):
        """提取第N集的道具并生成视觉提示词。"""
        with self.session() as s:
            book = s.get(Book, self.book_id)
            script = s.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == episode,
            ).first()
            if not script:
                raise ValueError(f"Episode {episode} script not found. Run 'script' first.")

            era_spec = self._get_era_spec_text(s)
            prompt = load_prompt(
                "scene/props",
                episode=episode,
                era_spec=era_spec,
                script_content=script.content[:config.SCRIPT_EXCERPT_CHARS],
                genre_name=self.genre.name,
            )

            result = call_llm_json(prompt, estimated_tokens=config.ESTIMATED_TOKENS_CHAPTER)
            if isinstance(result, dict):
                props = result.get("props", [result])
            else:
                props = result
            if isinstance(props, dict):
                props = [props]
            props = [self._canonicalize_prop_payload(prop, episode) for prop in props if isinstance(prop, dict)]

            # 预加载该 book 下已有道具（用于去重）
            existing_props = {
                (p.name, p.category): p
                for p in s.query(VisualProp).filter(VisualProp.book_id == self.book_id).all()
            }

            for prop in props:
                eps = prop.get("episodes", [episode])
                if isinstance(eps, int):
                    eps = [eps]
                char_associated = prop.get("associated_characters", [])
                if isinstance(char_associated, list):
                    char_associated = json.dumps(char_associated, ensure_ascii=False)

                prop_name = prop.get("name", "")
                prop_category = prop.get("category", "")

                # 去重：检查 name+categor 是否重复，若重复则只更新 episodes
                existing = existing_props.get((prop_name, prop_category)) or \
                           s.query(VisualProp).filter(
                               VisualProp.book_id == self.book_id,
                               VisualProp.name == prop_name,
                           ).first()
                if existing:
                    existing.description = prop.get("description", existing.description)
                    existing.associated_characters = char_associated or existing.associated_characters
                    existing.time_period = prop.get("time_period", existing.time_period)
                    existing.visual_prompt_en = prop.get("visual_prompt_en", existing.visual_prompt_en)
                    existing.visual_prompt_zh = prop.get("visual_prompt_zh", existing.visual_prompt_zh)
                    existing.importance = prop.get("importance", existing.importance)
                    existing.episodes = json.dumps(eps, ensure_ascii=False)
                    from datetime import datetime
                    existing.updated_at = datetime.utcnow()
                else:
                    s.add(VisualProp(
                        book_id=self.book_id,
                        book_title=book.title,
                        name=prop.get("name", ""),
                        category=prop.get("category", ""),
                        description=prop.get("description", ""),
                        associated_characters=char_associated or "[]",
                        episodes=json.dumps(eps, ensure_ascii=False),
                        time_period=prop.get("time_period", ""),
                        visual_prompt_en=prop.get("visual_prompt_en", ""),
                        visual_prompt_zh=prop.get("visual_prompt_zh", ""),
                        core_prompt_en=prop.get("core_prompt_en", ""),
                        core_prompt_zh=prop.get("core_prompt_zh", ""),
                        style_ref_en=prop.get("style_ref_en", ""),
                        style_ref_zh=prop.get("style_ref_zh", ""),
                        importance=prop.get("importance", "medium"),
                    ))
            s.commit()

        self.log(f"props episode {episode}: {len(props)} props")
        return props

    # ============================================================
    # 8c. Locations
    # ============================================================
    def run_locations(self, episode: int):
        """提取第N集的场景并生成视觉提示词。"""
        with self.session() as s:
            book = s.get(Book, self.book_id)
            script = s.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == episode,
            ).first()
            if not script:
                raise ValueError(f"Episode {episode} script not found. Run 'script' first.")

            era_spec = self._get_era_spec_text(s)
            prompt = load_prompt(
                "scene/locations",
                episode=episode,
                era_spec=era_spec,
                script_content=script.content[:config.SCRIPT_EXCERPT_CHARS],
                genre_name=self.genre.name,
            )

            result = call_llm_json(prompt, estimated_tokens=config.ESTIMATED_TOKENS_CHAPTER)
            if isinstance(result, dict):
                locations = result.get("locations", result.get("scenes", [result]))
            else:
                locations = result
            if isinstance(locations, dict):
                locations = [locations]
            locations = [self._canonicalize_location_payload(loc, episode) for loc in locations if isinstance(loc, dict)]

            # 预加载该 book 下已有场景（用于去重）
            existing_locs = {
                (loc.name, loc.category): loc
                for loc in s.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).all()
            }

            for loc in locations:
                eps = loc.get("episodes", [episode])
                if isinstance(eps, int):
                    eps = [eps]

                loc_name = loc.get("name", "")
                loc_category = loc.get("category", "")

                existing = existing_locs.get((loc_name, loc_category)) or \
                           s.query(VisualLocation).filter(
                               VisualLocation.book_id == self.book_id,
                               VisualLocation.name == loc_name,
                           ).first()
                if existing:
                    existing.style = loc.get("style", existing.style)
                    existing.description = loc.get("description", existing.description)
                    existing.color_palette = loc.get("color_palette", existing.color_palette)
                    existing.lighting_mood = loc.get("lighting_mood", existing.lighting_mood)
                    existing.visual_prompt_en = loc.get("visual_prompt_en", existing.visual_prompt_en)
                    existing.visual_prompt_zh = loc.get("visual_prompt_zh", existing.visual_prompt_zh)
                    existing.importance = loc.get("importance", existing.importance)
                    existing.episodes = json.dumps(eps, ensure_ascii=False)
                    from datetime import datetime
                    existing.updated_at = datetime.utcnow()
                else:
                    s.add(VisualLocation(
                        book_id=self.book_id,
                        book_title=book.title,
                        name=loc.get("name", ""),
                        category=loc.get("category", ""),
                        style=loc.get("style", ""),
                        description=loc.get("description", ""),
                        color_palette=loc.get("color_palette", ""),
                        lighting_mood=loc.get("lighting_mood", ""),
                        key_props=loc.get("key_props", "[]"),
                        episodes=json.dumps(eps, ensure_ascii=False),
                        time_period=loc.get("time_period", ""),
                        visual_prompt_en=loc.get("visual_prompt_en", ""),
                        visual_prompt_zh=loc.get("visual_prompt_zh", ""),
                        core_prompt_en=loc.get("core_prompt_en", ""),
                        core_prompt_zh=loc.get("core_prompt_zh", ""),
                        scene_mood_en=loc.get("scene_mood_en", ""),
                        scene_mood_zh=loc.get("scene_mood_zh", ""),
                        importance=loc.get("importance", "medium"),
                    ))
            s.commit()

        self.log(f"locations episode {episode}: {len(locations)} locations")
        return locations

    # ============================================================
    # 8d. Makeup
    # ============================================================
    def run_makeup(self, episode: int):
        """精调第N集所有出场角色的定妆照提示词。"""
        with self.session() as s:
            book = s.get(Book, self.book_id)
            script = s.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == episode,
            ).first()
            if not script:
                raise ValueError(f"Episode {episode} script not found. Run 'script' first.")

            era_spec = self._get_era_spec_text(s)

            # 获取该集涉及的角色列表（从 outline 或剧本内容推断）
            ep_chars = self._get_episode_characters(s, episode)
            if not ep_chars:
                self.log(f"episode {episode}: no characters found, skipping")
                return []

            # 获取本集已有的道具和场景（辅助上下文）
            props_text = self._get_episode_props_text(s, episode)
            locs_text = self._get_episode_locations_text(s, episode)
            props_locs = f"## 道具\n{props_text}\n## 场景\n{locs_text}" if props_text or locs_text else ""

            # 删除旧 makeup 数据
            s.query(VisualMakeup).filter(
                VisualMakeup.book_id == self.book_id,
                VisualMakeup.episode == episode,
            ).delete()
            s.commit()

            results = []
            for char_name in ep_chars:
                # 获取角色基础画像
                base_portrait = self._get_character_portrait_text(s, char_name, episode)
                if not base_portrait:
                    self.log(f"  skip {char_name}: no portrait data")
                    continue

                # 获取剧本中该角色的出场戏份
                char_scenes = self._extract_character_scenes(script.content, char_name)
                if not char_scenes:
                    self.log(f"  skip {char_name}: no scenes in episode {episode}")
                    continue

                # 构建同集其他角色紧凑信息
                other_chars = [c for c in ep_chars if c != char_name]
                other_text = ""
                for oc in other_chars[:5]:
                    op = self._get_character_portrait_text(s, oc, episode)
                    if op:
                        other_text += f"\n### {oc}\n{op[:500]}\n"

                prompt = load_prompt(
                    "scene/makeup",
                    character_name=char_name,
                    episode=episode,
                    era_spec=era_spec,
                    base_portrait=base_portrait[:config.PORTRAIT_EXCERPT_CHARS],
                    character_scenes=char_scenes[:config.CHAR_INFO_CHARS],
                    other_characters_compact=other_text[:config.PROPS_LOCS_CHARS] or "无",
                    episode_props_locations=props_locs[:config.PROPS_LOCS_CHARS] or "无",
                    genre_name=self.genre.name,
                )

                try:
                    result = call_llm_json(prompt, estimated_tokens=config.ESTIMATED_TOKENS_CHAPTER)
                except Exception as e:
                    self.log(f"  {char_name}: makeup failed: {e}")
                    continue

                # 保存
                # 强制用 profile.signature_outfit 覆盖 LLM 输出的服装（防止 LLM 擅自改服装类别）
                prof = s.query(CharacterProfile).filter(
                    CharacterProfile.book_id == self.book_id,
                    CharacterProfile.name == char_name,
                ).first()
                forced_outfit = (prof.signature_outfit if prof and prof.signature_outfit
                                 and prof.signature_outfit.strip() not in ('', '无描述', '未知')
                                 else result.get("refined_outfit", ""))
                forced_accessories = (prof.accessories if prof and prof.accessories
                                      and prof.accessories.strip() not in ('', '无描述', '未知')
                                      else result.get("refined_accessories", ""))

                scope = self._normalize_makeup_scope(result)
                stage_name = self._default_stage_name(scope, episode, result)
                shot_ids = result.get("shot_ids", [])
                if not isinstance(shot_ids, list):
                    shot_ids = []
                normalized_shot_ids = [str(item).strip() for item in shot_ids if str(item).strip()]
                result["scope"] = scope
                result["stage_name"] = stage_name
                result["shot_ids"] = normalized_shot_ids
                result["refined_outfit"] = forced_outfit
                result["refined_accessories"] = forced_accessories
                variant_fields = canonicalize_variant_prompt_inputs(
                    identity=str(result.get("identity", "") or (prof.identity if prof else "")),
                    makeup_expression=_first_non_empty(str(result.get("makeup_spec", "") or ""), str(result.get("expression_mood", "") or ""), ""),
                    scene_effects=str(result.get("scene_prompt_zh", "") or ""),
                    hairstyle=str(result.get("hair_style", "") or ""),
                    outfit=forced_outfit,
                    accessories=forced_accessories,
                )
                result["identity"] = variant_fields["identity"]
                result["makeup_spec"] = variant_fields["makeup_expression"]
                result["scene_prompt_zh"] = variant_fields["scene_effects"]
                result["hair_style"] = variant_fields["hairstyle"] or str(result.get("hair_style", "") or "")
                result["refined_outfit"] = variant_fields["outfit"] or forced_outfit
                result["refined_accessories"] = variant_fields["accessories"] or forced_accessories
                rendered_prompt_zh = self._render_makeup_prompt_from_result(char_name, episode, prof, result) if prof else str(result.get("visual_prompt_zh", "") or "")
                meta_info = {
                    "scope": scope,
                    "template_version": "makeup_six_grid_v2",
                    "rendered_from_template": True,
                    "prompt_source": "scene/makeup",
                    "structured_result": result,
                    "episode": episode,
                    "character_name": char_name,
                }

                s.add(VisualMakeup(
                    book_id=self.book_id,
                    book_title=book.title,
                    episode=episode,
                    character_name=char_name,
                    stage_name=stage_name,
                    refined_outfit=forced_outfit,
                    refined_accessories=forced_accessories,
                    makeup_spec=result.get("makeup_spec", ""),
                    hair_style=result.get("hair_style", ""),
                    expression_mood=result.get("expression_mood", ""),
                    visual_prompt_en=result.get("visual_prompt_en", ""),
                    visual_prompt_zh=rendered_prompt_zh,
                    core_prompt_en=result.get("core_prompt_en", ""),
                    core_prompt_zh=result.get("core_prompt_zh", ""),
                    outfit_prompt_en=result.get("outfit_prompt_en", ""),
                    outfit_prompt_zh=result.get("outfit_prompt_zh", ""),
                    scene_prompt_en=result.get("scene_prompt_en", ""),
                    scene_prompt_zh=result.get("scene_prompt_zh", ""),
                    consistency_notes=result.get("consistency_notes", ""),
                    meta_info=json.dumps(meta_info, ensure_ascii=False),
                    shot_ids=json.dumps(normalized_shot_ids, ensure_ascii=False),
                ))
                results.append(result)
                self.log(f"  [makeup] {char_name} (ep {episode})")

            s.commit()
            self._save_makeup_outputs(book.title, episode)

        self.log(f"makeup episode {episode}: {len(results)} characters")
        return results

    # ============================================================
    # 辅助方法
    # ============================================================
    def _canonicalize_prop_payload(self, prop: dict, episode: int) -> dict:
        payload = dict(prop or {})
        name = str(payload.get("name", "") or "").strip()
        category = str(payload.get("category", "") or "").strip() or "未分类道具"
        description = self._normalize_asset_text(str(payload.get("description", "") or ""), "道具描述待补充")
        visual_prompt_zh = self._normalize_asset_text(str(payload.get("visual_prompt_zh", "") or ""), description)
        core_prompt_zh = self._normalize_asset_text(str(payload.get("core_prompt_zh", "") or ""), description)
        style_ref_zh = self._normalize_asset_text(str(payload.get("style_ref_zh", "") or ""), "写实影视道具设定图")
        importance = self._normalize_importance(str(payload.get("importance", "") or "medium"))
        associated_characters = payload.get("associated_characters", [])
        if not isinstance(associated_characters, list):
            associated_characters = []
        episodes = payload.get("episodes", [episode])
        if isinstance(episodes, int):
            episodes = [episodes]
        if not isinstance(episodes, list) or not episodes:
            episodes = [episode]
        payload.update(
            {
                "name": name or "未命名道具",
                "category": category,
                "description": description,
                "visual_prompt_zh": visual_prompt_zh,
                "core_prompt_zh": core_prompt_zh,
                "style_ref_zh": style_ref_zh,
                "importance": importance,
                "associated_characters": associated_characters,
                "episodes": episodes,
            }
        )
        return payload

    def _canonicalize_location_payload(self, loc: dict, episode: int) -> dict:
        payload = dict(loc or {})
        name = str(payload.get("name", "") or "").strip()
        category = str(payload.get("category", "") or "").strip() or "未分类场景"
        style = self._normalize_asset_text(str(payload.get("style", "") or ""), "写实影视场景")
        description = self._normalize_asset_text(str(payload.get("description", "") or ""), "场景描述待补充")
        color_palette = self._normalize_asset_text(str(payload.get("color_palette", "") or ""), "低饱和电影色调")
        lighting_mood = self._normalize_asset_text(str(payload.get("lighting_mood", "") or ""), "柔和自然光")
        visual_prompt_zh = self._normalize_asset_text(str(payload.get("visual_prompt_zh", "") or ""), description)
        core_prompt_zh = self._normalize_asset_text(str(payload.get("core_prompt_zh", "") or ""), description)
        scene_mood_zh = self._normalize_asset_text(str(payload.get("scene_mood_zh", "") or ""), lighting_mood)
        importance = self._normalize_importance(str(payload.get("importance", "") or "medium"))
        episodes = payload.get("episodes", [episode])
        if isinstance(episodes, int):
            episodes = [episodes]
        if not isinstance(episodes, list) or not episodes:
            episodes = [episode]
        payload.update(
            {
                "name": name or "未命名场景",
                "category": category,
                "style": style,
                "description": description,
                "color_palette": color_palette,
                "lighting_mood": lighting_mood,
                "visual_prompt_zh": visual_prompt_zh,
                "core_prompt_zh": core_prompt_zh,
                "scene_mood_zh": scene_mood_zh,
                "importance": importance,
                "episodes": episodes,
            }
        )
        return payload

    def _normalize_asset_text(self, value: str, fallback: str) -> str:
        text = str(value or "").strip()
        if not text or text in {"未知", "无描述", "无"}:
            return fallback
        parts = [item.strip() for item in re.split(r"[，,。；;]", text) if item.strip()]
        deduped: list[str] = []
        for part in parts:
            if any(part == existing or part in existing for existing in deduped):
                continue
            deduped = [existing for existing in deduped if existing not in part]
            deduped.append(part)
        return "，".join(deduped) if deduped else fallback

    def _normalize_importance(self, value: str) -> str:
        text = str(value or "").strip().lower()
        if text in {"high", "medium", "low"}:
            return text
        mapping = {
            "高": "high",
            "重要": "high",
            "核心": "high",
            "中": "medium",
            "一般": "medium",
            "低": "low",
            "次要": "low",
        }
        return mapping.get(text, "medium")

    def _get_era_spec_text(self, session) -> str:
        """获取时代规范文本。"""
        era = session.query(VisualEraSpec).filter(
            VisualEraSpec.book_id == self.book_id
        ).first()
        if not era:
            return "（未扫描时代规范，请先运行 era_scan）"

        lines = [
            f"时间范围: {era.timeline_start} ~ {era.timeline_end}",
            f"服饰规范: {era.clothing_spec}",
            f"建筑风格: {era.architecture_spec}",
            f"色彩基调: {era.color_palette}",
            f"道具特征: {era.prop_spec}",
            f"色彩曲线: {era.color_curve}",
            f"赛道适配: {era.genre_adapt_rules}",
        ]
        # 附加 periods 细节
        try:
            periods = safe_json_loads(era.time_periods, [])
            for p in periods:
                lines.append(f"  {p.get('period','')} ({p.get('years','')}): {p.get('description','')}")
        except (json.JSONDecodeError, TypeError):
            pass
        return "\n".join(lines)

    def _get_episode_characters(self, session, episode: int) -> list:
        """从脚本文件提取该集出场角色（与 portrait 取交集）。
        支持：
        - 对话行 "角色名：" 或 "**角色名：**"
        - 场景人物列表 "- 人物：A、B、C"
        - **场景** 标题后的破折号列表
        - 画面描述中的称谓（如"王强走上前"）
        """
        from models import Script
        script = session.query(Script).filter(
            Script.book_id == self.book_id,
            Script.episode == episode,
        ).first()
        if not script or not script.content:
            return self._guess_characters(session, episode)

        import re
        chars = set()
        skip_words = {'画面', '镜头', '旁白', '字幕', '内心', 'OS', '背景', '时间', '地点', '场', '特写', '慢镜头', '画外音', '切', '闪回'}

        # 第一遍：人物列表
        for line in script.content.split("\n"):
            line_stripped = line.strip()
            if '人物：' in line_stripped or '人物:' in line_stripped:
                # 格式: - 人物：王强、颜大海、两个打手
                _, _, rest = line_stripped.partition('人物')
                _, _, rest = rest.partition('：')
                if not rest:
                    _, _, rest = rest.partition(':')
                for part in re.split(r'[、,，\s]+', rest):
                    part = part.strip()
                    if part and len(part) >= 2 and re.match(r'^[\u4e00-\u9fff]+$', part):
                        if part not in skip_words:
                            chars.add(part)

            # 第二遍：**角色名：** 格式（Markdown 加粗对话行，两种冒号位置皆支持）
            # 格式1: **宋庭筠：** （标准）
            # 格式2: **宋庭筠：**（无空格）
            m = re.search(r'\*\*([\u4e00-\u9fff]{2,6})[：:]\*\*', line_stripped)
            if not m:
                m = re.search(r'\*\*([\u4e00-\u9fff]{2,6})\*\*[：:]', line_stripped)
            if m:
                name = m.group(1)
                if name not in skip_words:
                    chars.add(name)

            # 第三遍：场景画面描述中提及的中文人名
            # 如"王强走上前"、"颜夕被推进来"
            for name_match in re.finditer(r'[\u4e00-\u9fff]{2,6}(?=被)', line_stripped):
                name = name_match.group(0)
                if name not in skip_words:
                    chars.add(name)

        if not chars:
            return self._guess_characters(session, episode)

        existing_names = {c.name for c in session.query(CharacterProfile).filter(
            CharacterProfile.book_id == self.book_id
        ).all()}
        filtered = chars & existing_names
        if not filtered:
            return self._guess_characters(session, episode)

        profiles = session.query(CharacterProfile).filter(
            CharacterProfile.book_id == self.book_id,
            CharacterProfile.name.in_(filtered),
        ).all()
        order = {'main': 0, 'major': 1, 'guest': 2, 'minor': 3}
        profiles.sort(key=lambda p: order.get(p.importance, 99))
        return [p.name for p in profiles]

    def _guess_characters(self, session, episode: int) -> list:
        """从 portrait 数据推断角色。"""
        chars = session.query(CharacterProfile).filter(
            CharacterProfile.book_id == self.book_id
        ).order_by(CharacterProfile.importance.desc()).limit(10).all()
        return [c.name for c in chars]

    def _get_character_portrait_text(self, session, char_name: str, episode: int) -> str:
        """获取角色的画像文本（优先用阶段画像）。"""
        stage = session.query(CharacterStage).filter(
            CharacterStage.book_id == self.book_id,
            CharacterStage.character_name == char_name,
        ).first()
        if stage:
            return (
                f"阶段: {stage.stage_name} (Ch.{stage.chapter_start}-{stage.chapter_end})\n"
                f"时间线: {stage.timeline}\n"
                f"身份: {stage.identity}\n"
                f"年龄: {stage.age_description}\n"
                f"脸型: {stage.face_shape}\n"
                f"五官: {stage.facial_features}\n"
                f"体型: {stage.body_type}\n"
                f"肤色: {stage.skin_tone}\n"
                f"穿着: {stage.signature_outfit}\n"
                f"配饰: {stage.accessories}\n"
                f"气质: {stage.temperament}\n"
                f"氛围: {stage.vibe}\n"
                f"代表色: {stage.color_palette}\n"
                f"EN Prompt: {stage.visual_prompt_en[:300]}"
            )

        profile = session.query(CharacterProfile).filter(
            CharacterProfile.book_id == self.book_id,
            CharacterProfile.name == char_name,
        ).first()
        if profile:
            # 是否需要物种标记
            identity = profile.identity or ""
            species_prefix = f"[物种: {profile.identity}] " if any(k in identity for k in ["猴","狐狸","动物","精怪","鬼","蛇","狼"]) else ""
            return (
                f"性别: {profile.gender}\n"
                f"身份: {species_prefix}{profile.identity}\n"
                f"年龄: {profile.age_range}\n"
                f"脸型: {profile.face_shape}\n"
                f"五官: {profile.facial_features}\n"
                f"体型: {profile.body_type}\n"
                f"穿着: {profile.signature_outfit}\n"
                f"气质: {profile.temperament}\n"
                f"氛围: {profile.vibe}\n"
                f"EN Prompt: {profile.visual_prompt_en[:300]}"
            )
        return ""

    def _extract_character_scenes(self, script_content: str, char_name: str) -> str:
        """从剧本中提取某个角色的出场戏份。"""
        lines = []
        current_scene = ""
        in_relevant = False
        for line in script_content.split("\n"):
            stripped = line.strip()
            # 场景标题
            if stripped.startswith("【") or stripped.startswith("###") or stripped.startswith("##"):
                if stripped.startswith("【"):
                    current_scene = stripped
                in_relevant = False
            # 角色名出现在对话或描述中
            if char_name in stripped:
                in_relevant = True
                if current_scene and current_scene not in "".join(lines[-3:]):
                    lines.append(f"\n--- {current_scene} ---")
                lines.append(stripped)
            elif in_relevant:
                # 收集该角色的上下文行（最多3行）
                if stripped and not stripped.startswith("【") and not stripped.startswith("##"):
                    lines.append(stripped)
        return "\n".join(lines[:100])

    def _get_episode_props_text(self, session, episode: int) -> str:
        """获取本集道具信息。"""
        props = session.query(VisualProp).filter(
            VisualProp.book_id == self.book_id
        ).all()
        lines = []
        for p in props:
            try:
                eps = safe_json_loads(p.episodes, [])
            except (json.JSONDecodeError, TypeError):
                eps = []
            if episode in eps:
                lines.append(f"- {p.name} ({p.category}): {p.description[:100]}")
        return "\n".join(lines)

    def _get_episode_locations_text(self, session, episode: int) -> str:
        """获取本集场景信息。"""
        locs = session.query(VisualLocation).filter(
            VisualLocation.book_id == self.book_id
        ).all()
        lines = []
        for loc in locs:
            try:
                eps = safe_json_loads(loc.episodes, [])
            except (json.JSONDecodeError, TypeError):
                eps = []
            if episode in eps:
                lines.append(f"- {loc.name} ({loc.category}): {loc.description[:100]}")
        return "\n".join(lines)

    # ============================================================
    # 输出保存
    # ============================================================
    def _llm_infer_makeup_fields(self, char_name: str, makeup, profile) -> dict:
        """用 LLM 推断缺失的定妆字段，避免出现'未知''无描述'。优先使用 profile 已有值。"""
        from models import BookBible, Script

        with self.session() as s:
            bible = s.query(BookBible).filter(
                BookBible.book_id == self.book_id
            ).first()
            bible_text = bible.content[:config.RULES_EXCERPT_CHARS] if bible else ''

            script = s.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == makeup.episode,
            ).first()
            script_text = ''
            if script:
                for line in script.content.split('\n'):
                    if char_name in line:
                        script_text += line + '\n'
                script_text = script_text[:config.TIMELINE_EXCERPT_CHARS]

        outfit = makeup.refined_outfit or (profile.signature_outfit or '')
        accessories = makeup.refined_accessories or (profile.accessories or '')
        hairstyle = makeup.hair_style or (profile.hairstyle or '')

        prompt = f"""你是一名专业的影视造型设计师。根据小说圣经和剧本上下文，为角色【{char_name}】合理推断定妆照所需的各个字段。

**重要规则**：如果已有明确的穿着/配饰/发型描述，必须直接使用，不得自行修改。

已有信息：
- 穿着：{outfit or '（缺失）'}
- 配饰：{accessories or '（缺失）'}
- 发型：{hairstyle or '（缺失）'}

小说圣经（部分）：
{bible_text}

剧本中该角色的出场：
{script_text}

请补齐以下 JSON 字段。**不要使用'未知''无描述'等占位词**——必须根据小说和剧本语境给出合理推断。
{{
  "age": "角色的精确年龄或年龄段，如'22岁'或'三十岁出头'",
  "identity": "角色的身份/职业",
  "temperament": "气质关键词，如'清冷、高傲'",
  "face_shape": "脸型，如'精致流畅的鹅蛋脸'或'轮廓分明的方脸'",
  "eyebrows": "眉毛特征，如'远山黛眉'或'浓密剑眉'",
  "eyes": "眼睛特征，如'凤眼微挑'或'深邃眼眸'",
  "nose": "鼻子特征，如'小巧挺直'或'高挺鼻梁'",
  "lips": "嘴唇特征，如'饱满红唇'或'薄唇浅笑'",
  "skin_tone": "肤色，如'白皙细腻'或'健康小麦色'",
  "marks": "显著特征，如'左眼角泪痣'或'无'",
  "hairstyle": "发型描述，如'大波浪卷发披肩'或'清爽短发'",
  "outfit": "当前阶段的具体服装",
  "accessories": "配饰描述"
}}"""

        try:
            result = call_llm_json(prompt, system="你是一名专业的影视造型设计师。输出 JSON，不允许使用'未知'等占位词。")
            return result if isinstance(result, dict) else {}
        except Exception as e:
            self.log(f"  [makeup] LLM推断失败 ({char_name}): {e}")
            return {}

    def _render_six_grid_sheet(self, char_name: str, gender: str, age: str, identity: str,
                                temperament: str, face_shape: str, eyebrows: str, eyes: str,
                                nose_desc: str, lips: str, skin_tone: str, marks: str,
                                hairstyle: str, outfit: str, accessories: str) -> str:
        """用六宫格模板渲染定妆照。"""
        gender_zh = {'男': '男性', '女': '女性', '未知': '男性'}.get(gender, '男性')
        return f"""人物定妆设定板，展示同一个角色的六个视角。
上排为脸部特写：正面、侧面、45度；
下排为全身展示：正面、侧面、背面。
六个视角必须是同一个人，保持面部一致性、发型一致性、服装一致性、体型一致性。
人物为：【{age}】岁的【中国/地区】【{gender_zh}】，身份是【{identity}】，气质【{temperament}】。
外貌特征：【{face_shape}】、【{eyebrows}】、【{eyes}】、【{nose_desc}】、【{lips}】、【{skin_tone}】、【{marks}】。
发型：【{hairstyle}】。
服装：【{outfit}】。
配饰：【{accessories}】。
表情自然克制，站姿标准，适合影视角色建模。
角色设定板，六宫格排版，纯白或浅灰背景，统一柔和影棚布光，超写实，电影级质感，高细节，8k，专业影视定妆照风格。"""

    def _normalize_makeup_scope(self, result: dict) -> str:
        scope = str(result.get("scope", "") or "").strip().lower()
        if scope in {"base_identity", "episode_default", "scene_variant", "shot_variant"}:
            return scope
        stage_name = str(result.get("stage_name", "") or "").strip().lower()
        if stage_name == "base_identity":
            return "base_identity"
        if stage_name.startswith("shot_"):
            return "shot_variant"
        if stage_name.startswith("scene_"):
            return "scene_variant"
        return "episode_default"

    def _default_stage_name(self, scope: str, episode: int, result: dict) -> str:
        stage_name = str(result.get("stage_name", "") or "").strip()
        if stage_name:
            return stage_name
        if scope == "base_identity":
            return "base_identity"
        if scope == "scene_variant":
            variant_name = str(result.get("variant_name", "") or "").strip() or "scene_variant"
            return f"scene_{variant_name}"
        if scope == "shot_variant":
            shot_ids = result.get("shot_ids", [])
            if isinstance(shot_ids, list) and shot_ids:
                return f"shot_{str(shot_ids[0]).strip()}"
            return f"shot_ep_{episode}"
        return f"episode_{episode}_default"

    def _render_makeup_prompt_from_result(self, character_name: str, episode: int, profile, result: dict) -> str:
        scope = self._normalize_makeup_scope(result)
        stage_name = self._default_stage_name(scope, episode, result)
        age = _first_non_empty(
            str(result.get("age", "") or ""),
            str(getattr(profile, "age_range", "") or ""),
            str(profile.precise_age) if getattr(profile, "precise_age", None) else "",
            "青年(18-35)",
        )
        region = _first_non_empty(
            str(result.get("region", "") or ""),
            str(getattr(profile, "nationality", "") or ""),
            "中国",
        )
        gender = _first_non_empty(str(result.get("gender", "") or ""), str(getattr(profile, "gender", "") or ""), "人物")
        identity = _first_non_empty(str(result.get("identity", "") or ""), str(getattr(profile, "identity", "") or ""), "角色")
        temperament = _first_non_empty(str(result.get("temperament", "") or ""), str(getattr(profile, "temperament", "") or ""), "克制")
        appearance = _first_non_empty(
            str(result.get("core_prompt_zh", "") or ""),
            str(getattr(profile, "facial_features", "") or ""),
            "五官稳定，角色辨识度明确",
        )
        canonical_fields = canonicalize_character_prompt_inputs(
            identity=identity,
            temperament=temperament,
            appearance=appearance,
        )
        identity = canonical_fields["identity"]
        temperament = canonical_fields["temperament"]
        appearance = canonical_fields["appearance"] or appearance
        hairstyle = _first_non_empty(str(result.get("hair_style", "") or ""), str(getattr(profile, "hairstyle", "") or ""), "保持基础发型")
        outfit = _first_non_empty(str(result.get("refined_outfit", "") or ""), str(getattr(profile, "signature_outfit", "") or ""), "基础服装")
        accessories = _first_non_empty(str(result.get("refined_accessories", "") or ""), str(getattr(profile, "accessories", "") or ""), "基础配饰")
        makeup_expression = _first_non_empty(str(result.get("makeup_spec", "") or ""), str(result.get("expression_mood", "") or ""), "自然克制")
        shot_ids = result.get("shot_ids", [])
        if not isinstance(shot_ids, list):
            shot_ids = []
        shot_label = "、".join([str(item).strip() for item in shot_ids if str(item).strip()]) or "-"
        variant_name = _first_non_empty(str(result.get("variant_name", "") or ""), stage_name)
        scene_effects = _first_non_empty(str(result.get("scene_prompt_zh", "") or ""), "无额外场景污染，保持标准影棚状态")
        variant_fields = canonicalize_variant_prompt_inputs(
            identity=identity,
            makeup_expression=makeup_expression,
            scene_effects=scene_effects,
            hairstyle=hairstyle,
            outfit=outfit,
            accessories=accessories,
        )
        identity = variant_fields["identity"]
        makeup_expression = variant_fields["makeup_expression"]
        scene_effects = variant_fields["scene_effects"]
        hairstyle = variant_fields["hairstyle"] or hairstyle
        outfit = variant_fields["outfit"] or outfit
        accessories = variant_fields["accessories"] or accessories
        prompt_bundle = compile_character_sheet_prompts(
            scope=scope,
            age=age,
            region=region,
            gender=gender,
            identity=identity,
            temperament=temperament,
            appearance=appearance,
            hairstyle=hairstyle,
            body_type=str(getattr(profile, "body_type", "") or ""),
            outfit=outfit,
            accessories=accessories,
            skin_tone=str(getattr(profile, "skin_tone", "") or ""),
            marks=str(getattr(profile, "distinguishing_marks", "") or ""),
            episode=episode,
            stage_name=stage_name,
            variant_name=variant_name,
            shot_label=shot_label,
            scene_effects=scene_effects,
            makeup_expression=makeup_expression,
        )
        return prompt_bundle["visual_prompt_zh"]

    def _six_grid_for_makeup(self, m, profile, inferred) -> str:
        """从 VisualMakeup 记录生成六宫格提示词。"""
        def _v(*vals):
            for v in vals:
                if v and v.strip() not in ('', '无描述', '未知', '无'):
                    return v
            return ''

        gender = profile.gender or '未知'
        age = _v(str(profile.precise_age) if profile.precise_age else '',
                 inferred.get('age', ''))
        identity = _v(profile.identity, inferred.get('identity'))
        temperament = _v(profile.temperament, inferred.get('temperament'))
        face_shape = _v(profile.face_shape, inferred.get('face_shape'))
        skin_tone = _v(profile.skin_tone, inferred.get('skin_tone'))
        marks = _v(profile.distinguishing_marks, inferred.get('marks'))
        hairstyle = _v(profile.hairstyle, inferred.get('hairstyle'))
        outfit = _v(m.refined_outfit, profile.signature_outfit,
                    inferred.get('outfit'))
        accessories = _v(m.refined_accessories, profile.accessories,
                         inferred.get('accessories'))
        eyebrows = inferred.get('eyebrows', '')
        eyes = inferred.get('eyes', '')
        nose_desc = inferred.get('nose', '')
        lips = inferred.get('lips', '')

        return self._render_six_grid_sheet(
            m.character_name, gender, age, identity, temperament,
            face_shape, eyebrows, eyes, nose_desc, lips,
            skin_tone, marks, hairstyle, outfit, accessories
        )

    def _save_makeup_outputs(self, title: str, episode: int):
        """保存定妆照输出文件。
        输出 visual/characters/{角色名}.md（追加每集段落）
        更新 visual/index.json 索引。
        兼容旧逻辑保留 makeups/ 单集文件。"""
        import json as _json
        import re as _re

        with self.session() as s:
            makeups = s.query(VisualMakeup).filter(
                VisualMakeup.book_id == self.book_id,
                VisualMakeup.episode == episode,
            ).order_by(VisualMakeup.character_name).all()

            if not makeups:
                return

            visual_dir = config.output_path(title, "visual")
            chars_dir = visual_dir / "characters"
            chars_dir.mkdir(parents=True, exist_ok=True)

            # 读/建 index.json
            index_path = visual_dir / "index.json"
            if index_path.exists():
                index = safe_json_loads(index_path.read_text(encoding='utf-8'), {})
            else:
                index = {}

            episode_key = str(episode)
            char_names = []

            for m in makeups:
                profile = s.query(CharacterProfile).filter(
                    CharacterProfile.book_id == self.book_id,
                    CharacterProfile.name == m.character_name,
                ).first()
                if not profile:
                    continue

                char_names.append(m.character_name)
                inferred = self._llm_infer_makeup_fields(m.character_name, m, profile)
                six_grid = self._six_grid_for_makeup(m, profile, inferred)

                # 追加到角色文件
                char_path = chars_dir / f"{m.character_name}.md"
                section = f"\n## 第{episode:02d}集\n\n{six_grid}\n"
                if char_path.exists():
                    existing = char_path.read_text(encoding='utf-8')
                    pattern = rf'## 第{episode:02d}集.*?(?=\n## |\Z)'
                    if _re.search(pattern, existing, _re.DOTALL):
                        existing = _re.sub(pattern, section.strip(), existing)
                    else:
                        existing += '\n' + section
                    char_path.write_text(existing, encoding='utf-8')
                else:
                    header = f"# {m.character_name}\n"
                    char_path.write_text(header + section, encoding='utf-8')

            # 更新 index.json
            index[episode_key] = {
                "characters": char_names,
            }
            index_path.write_text(_json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')

            self.log(f"visual/characters/ saved {len(makeups)} characters for ep {episode}")

            # 兼容旧逻辑：保留 makeups/ 单集文件
            md_lines = [f"# 第{episode:02d}集 - 定妆照\n"]
            for m in makeups:
                profile = s.query(CharacterProfile).filter(
                    CharacterProfile.book_id == self.book_id,
                    CharacterProfile.name == m.character_name,
                ).first()
                if not profile:
                    continue
                inferred = self._llm_infer_makeup_fields(m.character_name, m, profile)
                six_grid = self._six_grid_for_makeup(m, profile, inferred)
                md_lines.append(f"\n---\n### {m.character_name}\n\n{six_grid}\n")

            md_path = config.output_path(title, "makeups", f"第{episode:02d}集定妆照.md")
            md_path.write_text("\n".join(md_lines), encoding="utf-8")
            self.log(f"saved {md_path}")

    def save_era_spec_output(self, title: str):
        """保存时代规范输出文件。"""
        with self.session() as s:
            era = s.query(VisualEraSpec).filter(
                VisualEraSpec.book_id == self.book_id
            ).first()
            if not era:
                return

            lines = [f"# {title} - 时代妆造规范\n"]
            lines.append(f"\n## 时间范围")
            lines.append(f"{era.timeline_start} ~ {era.timeline_end}")
            try:
                periods = safe_json_loads(era.time_periods, [])
                if periods:
                    lines.append(f"\n### 时间分期")
                    for p in periods:
                        lines.append(f"- {p.get('period','')} ({p.get('years','')})")
                        desc = p.get('description', '')
                        if desc:
                            lines.append(f"  {desc}")
            except (json.JSONDecodeError, TypeError):
                pass
            lines.append(f"\n## 服饰规范\n{era.clothing_spec}")
            lines.append(f"\n## 建筑风格\n{era.architecture_spec}")
            lines.append(f"\n## 环境特征\n{era.environment_spec}")
            lines.append(f"\n## 色彩基调\n{era.color_palette}")
            lines.append(f"\n## 色彩曲线\n{era.color_curve}")
            lines.append(f"\n## 道具特征\n{era.prop_spec}")
            lines.append(f"\n## 赛道适配\n{era.genre_adapt_rules}")

            md_path = config.output_path(title, "visual", "时代妆造规范.md")
            md_path.write_text("\n".join(lines), encoding="utf-8")
            self.log(f"saved {md_path}")

    def save_props_output(self, title: str):
        """保存道具视觉输出文件。"""
        with self.session() as s:
            props = s.query(VisualProp).filter(
                VisualProp.book_id == self.book_id
            ).order_by(VisualProp.category, VisualProp.name).all()

            if not props:
                return

            # JSON
            data = [{
                "name": p.name, "category": p.category,
                "description": p.description,
                "associated_characters": p.associated_characters,
                "episodes": p.episodes,
                "time_period": p.time_period,
                "visual_prompt_en": p.visual_prompt_en,
                "visual_prompt_zh": p.visual_prompt_zh,
                "importance": p.importance,
            } for p in props]
            json_path = config.output_path(title, "visual", "道具提示词.json")
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            # MD
            md_lines = [f"# {title} - 关键道具视觉提示词\n"]
            current_cat = None
            for p in props:
                if p.category != current_cat:
                    current_cat = p.category
                    md_lines.append(f"\n## {current_cat}\n")
                md_lines.append(f"\n### {p.name}")
                md_lines.append(f"**描述：** {p.description}")
                md_lines.append(f"**时代：** {p.time_period}")
                md_lines.append(f"**重要性：** {p.importance}")
                md_lines.append(f"\n**EN Prompt:**\n```\n{p.visual_prompt_en}\n```")
                md_lines.append(f"\n**ZH Prompt:**\n```\n{p.visual_prompt_zh}\n```")

            md_path = config.output_path(title, "visual", "道具提示词.md")
            md_path.write_text("\n".join(md_lines), encoding="utf-8")
            self.log(f"saved props output")

    def save_locations_output(self, title: str):
        """保存场景视觉输出文件。"""
        with self.session() as s:
            locs = s.query(VisualLocation).filter(
                VisualLocation.book_id == self.book_id
            ).order_by(VisualLocation.category, VisualLocation.name).all()

            if not locs:
                return

            # JSON
            data = [{
                "name": loc.name, "category": loc.category,
                "style": loc.style, "description": loc.description,
                "color_palette": loc.color_palette,
                "lighting_mood": loc.lighting_mood,
                "key_props": loc.key_props, "episodes": loc.episodes,
                "time_period": loc.time_period,
                "visual_prompt_en": loc.visual_prompt_en,
                "visual_prompt_zh": loc.visual_prompt_zh,
                "importance": loc.importance,
            } for loc in locs]
            json_path = config.output_path(title, "visual", "场景提示词.json")
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            # MD
            md_lines = [f"# {title} - 核心场景视觉提示词\n"]
            current_cat = None
            for loc in locs:
                if loc.category != current_cat:
                    current_cat = loc.category
                    md_lines.append(f"\n## {current_cat}\n")
                md_lines.append(f"\n### {loc.name}")
                md_lines.append(f"**风格：** {loc.style}")
                md_lines.append(f"**描述：** {loc.description}")
                md_lines.append(f"**色调：** {loc.color_palette}")
                md_lines.append(f"**光影：** {loc.lighting_mood}")
                md_lines.append(f"**时代：** {loc.time_period}")
                md_lines.append(f"\n**EN Prompt:**\n```\n{loc.visual_prompt_en}\n```")
                md_lines.append(f"\n**ZH Prompt:**\n```\n{loc.visual_prompt_zh}\n```")

            md_path = config.output_path(title, "visual", "场景提示词.md")
            md_path.write_text("\n".join(md_lines), encoding="utf-8")
            self.log(f"saved locations output")
