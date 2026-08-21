"""Storyboard Agent — 分镜工程。

按场景（scene）粒度生成结构化分镜表。
Episode Orchestrator 负责拆场景、调度、合并全局 shot_id。
"""
import json
import re
from datetime import datetime
from typing import Optional

import config
from core.llm import call_llm_json
from core.prompts import load_prompt, PROMPTS_DIR
from core.production_skill import build_production_skill_prompt_block
from models import (
    Session, Book, Script,
    VisualLocation, VisualProp, VisualMakeup, VisualEraSpec,
    SceneCharacter, SceneProp,
    StoryboardShot,
)
from agents.base import BaseAgent
from core import safe_json_loads
from core.validators.shadow_validation import shadow_validate_storyboard_shots
from genres import get_genre


class StoryboardAgent(BaseAgent):
    """分镜 Agent — 按场景生成结构化分镜表。"""

    name = "storyboard"

    def __init__(self, book_id: int, genre: str = "short_drama", progress_callback=None):
        super().__init__(book_id)
        self.genre = get_genre(genre)
        self.max_shots_per_scene = (4, 8)  # 每场景镜头数区间
        self.progress_callback = progress_callback

    def _notify_progress(self, stage: str, **payload):
        if not callable(self.progress_callback):
            return
        self.progress_callback({
            "stage": stage,
            **payload,
        })

    # ── Orchestrator ───────────────────────────────────────────

    def run(self, episode: int, resume_after_scene: str | None = None) -> list[dict]:
        """Orchestrator 入口：整集分镜生成。"""
        with self.session() as s:
            book = s.get(Book, self.book_id)
            script = s.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == episode,
            ).first()
            if not script:
                raise ValueError(
                    f"Episode {episode} script not found. Run 'script' first."
                )

            parsed_scene_blocks = self._parse_script_scene_blocks(script.content or "")
            if parsed_scene_blocks:
                all_shots = []
                preserved_shots = self._load_existing_episode_shots(s, episode, resume_after_scene)
                if preserved_shots:
                    all_shots.extend(preserved_shots)
                    self._notify_progress(
                        "resume_initialized",
                        episode=episode,
                        completed_scenes=self._count_preserved_scenes(preserved_shots),
                        resume_after_scene=resume_after_scene or "",
                    )
                self._notify_progress(
                    "scene_list_loaded",
                    episode=episode,
                    total_scenes=len(parsed_scene_blocks),
                    mode="fallback",
                )
                for scene_data in self._iter_resume_scenes(parsed_scene_blocks, resume_after_scene):
                    self._notify_progress(
                        "scene_started",
                        episode=episode,
                        scene_name=scene_data.get("name", ""),
                        mode="fallback",
                    )
                    all_shots.extend(self._generate_scene_shots_fallback(scene_data))
                    self._notify_progress(
                        "scene_completed",
                        episode=episode,
                        scene_name=scene_data.get("name", ""),
                        generated_shots=len(all_shots),
                        mode="fallback",
                    )
                all_shots = self._merge_and_renumber(all_shots)
                self._save_to_db(s, all_shots, episode)
                s.flush()
                shadow_validate_storyboard_shots(self.book_id, episode, all_shots, s)
                self._backfill_shot_ids(s, episode)
                s.commit()
                self.log(f"ep {episode}: fallback storyboard generated {len(all_shots)} shots")
                return all_shots

            # 1. 加载场景列表
            # 优先用 LLM 从剧本拆分（更准确定位实际出现的场景）
            # 视觉设定数据仅作为增强参考，不作为场景来源
            scenes = self._llm_split_scenes(s, episode, script.content or "")
            if not scenes:
                self.log(f"ep {episode}: LLM split returned empty, fallback to visual_locations")
                scenes = self._load_scenes(s, episode)
            preserved_shots = self._load_existing_episode_shots(s, episode, resume_after_scene)
            if preserved_shots:
                self._notify_progress(
                    "resume_initialized",
                    episode=episode,
                    completed_scenes=self._count_preserved_scenes(preserved_shots),
                    resume_after_scene=resume_after_scene or "",
                )
            self._notify_progress(
                "scene_list_loaded",
                episode=episode,
                total_scenes=len(scenes),
                mode="llm",
            )
            self.log(f"ep {episode}: {len(scenes)} scenes detected (from LLM split)")

            # 2. 按场景生成镜头
            all_shots = []
            if preserved_shots:
                all_shots.extend(preserved_shots)
            for scene_data in self._iter_resume_scenes(scenes, resume_after_scene):
                self._notify_progress(
                    "scene_started",
                    episode=episode,
                    scene_name=scene_data.get("name", ""),
                    mode="llm",
                )
                context = self._build_scene_context(
                    s, scene_data, episode, script.content or ""
                )
                scene_shots = self._generate_scene_shots(context, fallback_scene=scene_data)
                self.log(f"  {scene_data['name']}: {len(scene_shots)} shots")
                all_shots.extend(scene_shots)
                self._notify_progress(
                    "scene_completed",
                    episode=episode,
                    scene_name=scene_data.get("name", ""),
                    generated_shots=len(scene_shots),
                    mode="llm",
                )

            # 3. 合并 + 全局 shot_id
            all_shots = self._merge_and_renumber(all_shots)

            # 4. 写入 DB
            self._save_to_db(s, all_shots, episode)
            s.flush()
            shadow_validate_storyboard_shots(self.book_id, episode, all_shots, s)

            # 5. 回填 shot_ids → makeup / location / prop
            self._backfill_shot_ids(s, episode)
            s.commit()

        self.log(f"ep {episode}: total {len(all_shots)} shots saved")
        return all_shots

    def _parse_script_scene_blocks(self, content: str) -> list[dict]:
        """Parse structured markdown scenes directly from generated scripts."""
        pattern = re.compile(
            r"\*\*场景[一二三四五六七八九十0-9]+：\[(?P<name>[^\]]+)\]\*\*(?P<body>.*?)(?=\n---|\n\*\*场景[一二三四五六七八九十0-9]+：\[|\Z)",
            re.DOTALL,
        )
        scene_blocks = []
        for match in pattern.finditer(content):
            name = match.group("name").strip()
            body = match.group("body").strip()
            if not name or not body:
                continue
            scene_blocks.append(
                {
                    "name": name,
                    "prompt": body[:600],
                    "category": "",
                    "style": "",
                    "lighting": "",
                    "color_palette": "",
                    "script_block": body,
                }
            )
        return scene_blocks

    def _iter_resume_scenes(self, scenes: list[dict], resume_after_scene: str | None) -> list[dict]:
        if not resume_after_scene:
            return scenes
        anchor = str(resume_after_scene).strip()
        if not anchor:
            return scenes
        start_index = -1
        for index, scene in enumerate(scenes):
            if str(scene.get("name", "")).strip() == anchor:
                start_index = index
        if start_index < 0:
            return scenes
        return scenes[start_index + 1:]

    def _load_existing_episode_shots(self, session, episode: int, resume_after_scene: str | None) -> list[dict]:
        if not resume_after_scene:
            return []
        anchor = str(resume_after_scene).strip()
        if not anchor:
            return []

        rows = (
            session.query(StoryboardShot)
            .filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == episode,
            )
            .order_by(StoryboardShot.shot_id)
            .all()
        )
        preserved: list[dict] = []
        reached_anchor = False
        for row in rows:
            preserved.append({
                "scene_name": row.scene_name or "",
                "dialogue": row.dialogue or "",
                "duration": row.duration or 3,
                "camera_angle": row.camera_angle or "MS",
                "camera_movement": row.camera_movement or "static",
                "transition": row.transition or "cut",
                "lighting": row.lighting or "",
                "sound_effects": safe_json_loads(row.sound_effects, []) if getattr(row, "sound_effects", None) else [],
                "bgm_mood": row.bgm_mood or "",
                "start_state": row.start_state or "",
                "action_process": row.action_process or "",
                "end_state": row.end_state or "",
                "visual_prompt_static": row.visual_prompt_static or "",
                "visual_prompt_motion": row.visual_prompt_motion or "",
                "metadata": {"source": "resume-preserved"},
            })
            if str(row.scene_name or "").strip() == anchor:
                reached_anchor = True
        return preserved if reached_anchor else []

    def _count_preserved_scenes(self, shots: list[dict]) -> int:
        seen: list[str] = []
        for shot in shots:
            scene_name = str(shot.get("scene_name", "")).strip()
            if scene_name and scene_name not in seen:
                seen.append(scene_name)
        return len(seen)

    def _generate_scene_shots_fallback(self, scene: dict) -> list[dict]:
        """Build a small deterministic storyboard from a structured script scene."""
        block = scene.get("script_block", "")
        dialogues = re.findall(r"\*\*([^*：\n]{1,20})：\*\*\s*([^\n]+)", block)
        narration_lines = [
            line.strip(" -*")
            for line in block.splitlines()
            if line.strip().startswith("**[") and line.strip().endswith("]**")
        ]

        opening = narration_lines[0] if narration_lines else scene.get("prompt", "")[:120]
        ending = narration_lines[-1] if narration_lines else opening
        primary_dialogue = "；".join(f"{speaker}：{text}" for speaker, text in dialogues[:2]) or "无对白"
        dynamic_action = narration_lines[1] if len(narration_lines) > 1 else primary_dialogue

        return [
            {
                "scene_name": scene["name"],
                "dialogue": "",
                "duration": 3,
                "camera_angle": "WS",
                "camera_movement": "push-in",
                "transition": "cut",
                "lighting": "natural",
                "sound_effects": [],
                "bgm_mood": "suspense",
                "start_state": opening[:160],
                "action_process": opening[:200],
                "end_state": dynamic_action[:160],
                "visual_prompt_static": f"{scene['name']}，建立场景镜头，突出环境、时间与氛围。{opening[:180]}",
                "visual_prompt_motion": f"镜头缓慢推进，建立场景关系，保持叙事清晰。{dynamic_action[:180]}",
                "metadata": {"source": "fallback-structured-script"},
            },
            {
                "scene_name": scene["name"],
                "dialogue": primary_dialogue[:220],
                "duration": 4,
                "camera_angle": "MS",
                "camera_movement": "static",
                "transition": "cut",
                "lighting": "motivated",
                "sound_effects": [],
                "bgm_mood": "dramatic",
                "start_state": opening[:160],
                "action_process": primary_dialogue[:220],
                "end_state": dynamic_action[:160],
                "visual_prompt_static": f"{scene['name']}，人物互动中景，表情与对白清晰。{primary_dialogue[:180]}",
                "visual_prompt_motion": f"人物对话镜头，保持稳定构图，突出冲突和信息传递。{dynamic_action[:180]}",
                "metadata": {"source": "fallback-structured-script"},
            },
            {
                "scene_name": scene["name"],
                "dialogue": "",
                "duration": 3,
                "camera_angle": "CU",
                "camera_movement": "tilt",
                "transition": "cut",
                "lighting": "contrast",
                "sound_effects": [],
                "bgm_mood": "tense",
                "start_state": dynamic_action[:160],
                "action_process": dynamic_action[:200],
                "end_state": ending[:160],
                "visual_prompt_static": f"{scene['name']}，情绪特写或动作细节收束镜头。{ending[:180]}",
                "visual_prompt_motion": f"用特写结束本场景，强调情绪变化或悬念。{ending[:180]}",
                "metadata": {"source": "fallback-structured-script"},
            },
        ]

    # ── 场景加载 ───────────────────────────────────────────────

    def _load_scenes(self, session, episode: int) -> list[dict]:
        """从 visual_locations 表加载该集已有场景。"""
        loc_rows = (
            session.query(VisualLocation)
            .filter(VisualLocation.book_id == self.book_id)
            .all()
        )
        ep_scenes = []
        for loc in loc_rows:
            eps = safe_json_loads(loc.episodes, [])
            if episode in eps:
                ep_scenes.append({
                    "name": loc.name,
                    "prompt": (
                        loc.visual_prompt_zh
                        or loc.core_prompt_zh
                        or loc.description
                        or ""
                    ),
                    "category": loc.category or "",
                    "style": loc.style or "",
                    "lighting": loc.lighting_mood or "",
                    "color_palette": loc.color_palette or "",
                })
        return ep_scenes

    def _llm_split_scenes(
        self, session, episode: int, script_content: str
    ) -> list[dict]:
        """用 LLM 从剧本中提取场景列表（fallback）。"""
        prompt = load_prompt(
            "storyboard/scene_split",
            episode=episode,
        )
        prompt = f"{build_production_skill_prompt_block(self.book_id, 'directing')}\n\n{prompt}"
        full_prompt = f"{prompt}\n\n## 剧本内容\n{script_content[:8000]}"
        result = call_llm_json(full_prompt, estimated_tokens=config.ESTIMATED_TOKENS_SMALL)
        if isinstance(result, dict):
            scenes = result.get("scenes", result.get("locations", []))
        else:
            scenes = result

        # 尝试从剧本按行号提取场景段落
        lines = script_content.split("\n")
        enriched = []
        for sc in scenes:
            name = sc.get("scene_name", "")
            start = sc.get("start_line", 1) - 1
            end = sc.get("end_line", len(lines))
            block = "\n".join(lines[start:end])
            enriched.append({
                "name": name,
                "prompt": block[:500],
                "category": "",
                "style": "",
                "lighting": "",
                "color_palette": "",
            })
        return enriched

    # ── 场景上下文构建 ─────────────────────────────────────────

    def _build_scene_context(
        self, session, scene: dict, episode: int, script_content: str
    ) -> dict:
        """为单场景构建 LLM 输入上下文。"""
        scene_name = scene["name"]

        # 读取剧本中该场景段落
        script_block = self._extract_scene_script_block(
            script_content, scene_name
        )

        # 角色上下文
        char_rows = (
            session.query(SceneCharacter)
            .filter(
                SceneCharacter.book_id == self.book_id,
                SceneCharacter.location_name == scene_name,
                SceneCharacter.episode == episode,
            )
            .all()
        )
        characters_context_lines = []
        for cr in char_rows:
            makeup = (
                session.query(VisualMakeup)
                .filter(
                    VisualMakeup.book_id == self.book_id,
                    VisualMakeup.episode == episode,
                    VisualMakeup.character_name == cr.character_name,
                )
                .first()
            )
            prompt_zh = ""
            if makeup:
                prompt_zh = (
                    makeup.visual_prompt_zh
                    or makeup.core_prompt_zh
                    or ""
                )[:200]
            state_info = cr.state or ""
            outfit_info = cr.outfit or state_info
            characters_context_lines.append(
                f"{cr.character_name} | 状态:{cr.state} "
                f"穿着:{outfit_info} 表情:{cr.expression} "
                f"| {prompt_zh}"
            )

        if not characters_context_lines:
            # fallback: 从 visual_makeups 表取所有该集角色的定妆提示词
            makeups = (
                session.query(VisualMakeup)
                .filter(
                    VisualMakeup.book_id == self.book_id,
                    VisualMakeup.episode == episode,
                )
                .all()
            )
            for m in makeups:
                prompt_zh = (
                    m.visual_prompt_zh or m.core_prompt_zh or ""
                )[:200]
                characters_context_lines.append(
                    f"{m.character_name} | {prompt_zh}"
                )

        # 道具上下文
        prop_rows = (
            session.query(SceneProp)
            .filter(
                SceneProp.book_id == self.book_id,
                SceneProp.location_name == scene_name,
                SceneProp.episode == episode,
            )
            .all()
        )
        props_context_lines = []
        for pr in prop_rows:
            prop_obj = (
                session.query(VisualProp)
                .filter(
                    VisualProp.book_id == self.book_id,
                    VisualProp.name == pr.prop_name,
                )
                .first()
            )
            desc = prop_obj.description if prop_obj else ""
            usage_info = (
                f"位置:{pr.placement} "
                f"使用人:{pr.in_use_by} "
                f"状态:{pr.condition}"
            )
            props_context_lines.append(f"{pr.prop_name} | {desc} | {usage_info}")

        if not props_context_lines:
            # fallback: 从 visual_props 表取该集道具
            props = (
                session.query(VisualProp)
                .filter(VisualProp.book_id == self.book_id)
                .all()
            )
            for p in props:
                eps_str = str(getattr(p, 'episodes', '') or '')
                try:
                    import json
                    eps = json.loads(eps_str) if eps_str.startswith('[') else []
                except Exception:
                    eps = []
                if episode in eps:
                    props_context_lines.append(
                        f"{p.name} | {p.description[:100]}"
                    )

        # 从 visual_locations 匹配场景视觉数据（不精确匹配也可以用模糊名）
        scene_prompt = scene.get("prompt", "")
        lighting_mood = scene.get("lighting", "")
        color_palette = scene.get("color_palette", "")
        if not scene_prompt:
            # 尝试在 visual_locations 中匹配
            loc_match = (
                session.query(VisualLocation)
                .filter(
                    VisualLocation.book_id == self.book_id,
                    VisualLocation.name.ilike(f"%{scene_name[:6]}%"),
                )
                .first()
            )
            if loc_match:
                scene_prompt = (
                    loc_match.visual_prompt_zh or loc_match.core_prompt_zh or loc_match.description or ""
                )
                if not lighting_mood:
                    lighting_mood = loc_match.lighting_mood or ""
                if not color_palette:
                    color_palette = loc_match.color_palette or ""

        return {
            "scene_name": scene_name,
            "scene_prompt": scene_prompt,
            "lighting_mood": lighting_mood,
            "color_palette": color_palette,
            "script_block": script_block[:config.SCENE_EXCERPT_CHARS],
            "characters_context": (
                "\n".join(characters_context_lines)
                or "(无结构化角色数据，需从剧本推断)"
            ),
            "props_context": (
                "\n".join(props_context_lines)
                or "(无结构化道具数据)"
            ),
        }

    # ── LLM 生成镜头 ───────────────────────────────────────────

    def _generate_scene_shots(self, context: dict, fallback_scene: dict | None = None) -> list[dict]:
        """调 LLM 生成单场景的 4-8 个镜头。"""
        prompt = load_prompt(
            "storyboard/scene_shots",
            scene_name=context["scene_name"],
            scene_prompt=context["scene_prompt"],
            lighting_mood=context["lighting_mood"],
            color_palette=context["color_palette"],
            script_block=context["script_block"],
            characters_context=context["characters_context"],
            props_context=context["props_context"],
            genre_name=self.genre.name,
        )
        prompt = f"{build_production_skill_prompt_block(self.book_id, 'directing')}\n\n{prompt}"
        try:
            result = call_llm_json(prompt, estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT)
            shots = self._normalize_scene_shot_payload(result, context["scene_name"])
            if not shots:
                self.log(f"  WARNING: LLM returned empty shots for {context['scene_name']}")
                return []
            return shots
        except ValueError as exc:
            lowered = str(exc).lower()
            if "failed to parse llm json response" not in lowered and "truncated" not in lowered:
                raise

            self.log(f"  WARNING: scene {context['scene_name']} parse failed, retry with compact prompt")
            self._notify_progress(
                "scene_retrying",
                scene_name=context["scene_name"],
                reason="llm_truncated",
            )
            compact_prompt = load_prompt(
                "storyboard/scene_shots",
                scene_name=context["scene_name"],
                scene_prompt=context["scene_prompt"],
                lighting_mood=context["lighting_mood"],
                color_palette=context["color_palette"],
                script_block=context["script_block"][: max(600, len(context["script_block"]) // 2)],
                characters_context=context["characters_context"][:400],
                props_context=context["props_context"][:240],
                genre_name=self.genre.name,
            ) + "\n\n补充约束：如果场景较长，请优先输出 4 个最关键镜头，确保 JSON 完整闭合，不要输出 5 个以上镜头。"
            compact_prompt = f"{build_production_skill_prompt_block(self.book_id, 'directing')}\n\n{compact_prompt}"
            try:
                retry_result = call_llm_json(compact_prompt, estimated_tokens=max(2000, config.ESTIMATED_TOKENS_DEFAULT // 2))
                shots = self._normalize_scene_shot_payload(retry_result, context["scene_name"])
                if not shots:
                    raise ValueError("LLM returned empty shots after compact retry")
                return shots
            except ValueError:
                if not fallback_scene:
                    raise
                self.log(f"  WARNING: scene {context['scene_name']} retry exhausted, fallback to structured storyboard")
                self._notify_progress(
                    "scene_fallback_used",
                    scene_name=context["scene_name"],
                    reason="llm_retry_exhausted",
                )
                return self._generate_scene_shots_fallback(fallback_scene)

    def _normalize_scene_shot_payload(self, result, scene_name: str) -> list[dict]:
        if isinstance(result, dict):
            shots = (
                result.get("shots")
                or result.get("scenes")
                or result.get("storyboard")
                or []
            )
        else:
            shots = result

        if not isinstance(shots, list):
            return []

        for shot in shots:
            if isinstance(shot, dict):
                shot["scene_name"] = scene_name
        return [shot for shot in shots if isinstance(shot, dict)]

    # ── 辅助方法 ───────────────────────────────────────────────

    def _extract_scene_script_block(
        self, content: str, scene_name: str
    ) -> str:
        """从剧本中提取该场景对应的段落。"""
        patterns = [
            rf"##\s*{re.escape(scene_name)}.*?(?=\n##\s|\Z)",
            rf"###\s*{re.escape(scene_name)}.*?(?=\n###\s|\n##\s|\Z)",
            rf"【{re.escape(scene_name)}】.*?(?=\n【|\Z)",
            rf"#\s*{re.escape(scene_name)}.*?(?=\n#\s|\Z)",
        ]
        for pat in patterns:
            m = re.search(pat, content, re.DOTALL)
            if m:
                return m.group(0).strip()

        # 无标题匹配：返回前 4000 字
        return content[:config.SCENE_EXCERPT_CHARS]

    def _backfill_shot_ids(self, session, episode: int):
        """分镜生成后，反向回填每个 VisualMakeup/Location/Prop 所关联的镜号列表。"""
        from core import safe_json_loads
        import json

        # 查本集所有 shot
        shots = (
            session.query(StoryboardShot)
            .filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == episode,
            )
            .order_by(StoryboardShot.shot_id)
            .all()
        )
        if not shots:
            return

        # 1) VisualMakeup ─ 按角色名匹配
        makeups = (
            session.query(VisualMakeup)
            .filter(
                VisualMakeup.book_id == self.book_id,
                VisualMakeup.episode == episode,
            )
            .all()
        )
        if makeups:
            # 查本集每个 scene 出场的角色
            scene_chars = (
                session.query(SceneCharacter)
                .filter(
                    SceneCharacter.book_id == self.book_id,
                    SceneCharacter.episode == episode,
                )
                .all()
            )
            # location_name → set[character_name]
            loc_chars: dict[str, set[str]] = {}
            for sc in scene_chars:
                loc_chars.setdefault(sc.location_name, set()).add(sc.character_name)

            for m in makeups:
                matched_shots = []
                for sh in shots:
                    if sh.scene_name in loc_chars and m.character_name in loc_chars[sh.scene_name]:
                        matched_shots.append(sh.shot_id)
                m.shot_ids = json.dumps(matched_shots, ensure_ascii=False)

        # 2) VisualLocation ─ 按场景名匹配
        locations = (
            session.query(VisualLocation)
            .filter(VisualLocation.book_id == self.book_id)
            .all()
        )
        for loc in locations:
            matched = [sh.shot_id for sh in shots if sh.scene_name == loc.name]
            loc.shot_ids = json.dumps(matched, ensure_ascii=False)

        # 3) VisualProp ─ 按道具名匹配
        scene_props = (
            session.query(SceneProp)
            .filter(
                SceneProp.book_id == self.book_id,
                SceneProp.episode == episode,
            )
            .all()
        )
        # location_name → set[prop_name]
        loc_props: dict[str, set[str]] = {}
        for sp in scene_props:
            loc_props.setdefault(sp.location_name, set()).add(sp.prop_name)

        props = (
            session.query(VisualProp)
            .filter(VisualProp.book_id == self.book_id)
            .all()
        )
        prop_name_map: dict[str, list[VisualProp]] = {}
        for p in props:
            prop_name_map.setdefault(p.name, []).append(p)

        for sh in shots:
            if sh.scene_name in loc_props:
                for pname in loc_props[sh.scene_name]:
                    for p in prop_name_map.get(pname, []):
                        current = safe_json_loads(p.shot_ids, [])
                        if sh.shot_id not in current:
                            current.append(sh.shot_id)
                            p.shot_ids = json.dumps(current, ensure_ascii=False)

        self.log(f"ep {episode}: backfilled shot_ids for makeups/locations/props")

    def _merge_and_renumber(self, shots: list[dict]) -> list[dict]:
        """合并所有场景分镜 + 分配全局 shot_id。"""
        for idx, shot in enumerate(shots, start=1):
            shot["shot_id"] = idx
        return shots

    def _save_to_db(self, session, shots: list[dict], episode: int):
        """批量写入 DB。"""
        # 删除旧数据
        session.query(StoryboardShot).filter(
            StoryboardShot.book_id == self.book_id,
            StoryboardShot.episode == episode,
        ).delete()

        now = datetime.utcnow()
        for shot in shots:
            s = StoryboardShot(
                book_id=self.book_id,
                episode=episode,
                scene_name=shot.get("scene_name", ""),
                shot_id=shot.get("shot_id", 0),
                dialogue=shot.get("dialogue", ""),
                duration=shot.get("duration", 3),
                camera_angle=shot.get("camera_angle", "MS"),
                camera_movement=shot.get("camera_movement", "static"),
                transition=shot.get("transition", "cut"),
                lighting=shot.get("lighting", ""),
                sound_effects=json.dumps(
                    shot.get("sound_effects", []), ensure_ascii=False
                ),
                bgm_mood=shot.get("bgm_mood", ""),
                start_state=shot.get("start_state", ""),
                action_process=shot.get("action_process", ""),
                end_state=shot.get("end_state", ""),
                visual_prompt_static=shot.get("visual_prompt_static", ""),
                visual_prompt_motion=shot.get("visual_prompt_motion", ""),
                visual_prompt_final="",
                asset_links="{}",
                asset_status="pending",
                meta_info=json.dumps(
                    shot.get("metadata", {}), ensure_ascii=False
                ),
                created_at=now,
                updated_at=now,
            )
            session.add(s)

    # ── 输出保存 ───────────────────────────────────────────────

    def save_storyboard_output(self, title: str, episode: int):
        """保存分镜输出到 outputs/{title}/storyboard/。"""
        with self.session() as s:
            shots = (
                s.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == self.book_id,
                    StoryboardShot.episode == episode,
                )
                .order_by(StoryboardShot.shot_id)
                .all()
            )
            if not shots:
                return

            output_dir = config.output_path(title, "storyboard")
            output_dir.mkdir(parents=True, exist_ok=True)

            # JSON
            data = []
            for sh in shots:
                data.append({
                    "id": sh.shot_id,
                    "scene_name": sh.scene_name,
                    "dialogue": sh.dialogue,
                    "duration": sh.duration,
                    "camera_angle": sh.camera_angle,
                    "camera_movement": sh.camera_movement,
                    "transition": sh.transition,
                    "lighting": sh.lighting,
                    "sound_effects": safe_json_loads(sh.sound_effects, []),
                    "bgm_mood": sh.bgm_mood,
                    "start_state": sh.start_state,
                    "action_process": sh.action_process,
                    "end_state": sh.end_state,
                    "visual_prompt_static": sh.visual_prompt_static,
                    "visual_prompt_motion": sh.visual_prompt_motion,
                    "visual_prompt_final": sh.visual_prompt_final,
                    "asset_links": safe_json_loads(sh.asset_links, {}),
                    "asset_status": sh.asset_status,
                })

            json_path = output_dir / f"第{episode:02d}集分镜.json"
            json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # MD（人类可读）
            md_lines = [f"# 第{episode:02d}集分镜\n"]
            for sh in data:
                md_lines.append(
                    f"\n---\n## 镜号 {sh['id']}  |  "
                    f"{sh['scene_name']}  |  "
                    f"{sh['camera_angle']}  |  "
                    f"{sh['duration']}s  |  "
                    f"{sh['camera_movement']}\n"
                )
                md_lines.append(f"**对白：** {sh['dialogue'] or '（无声）'}")
                md_lines.append(f"**光影：** {sh['lighting']}")
                md_lines.append(f"**BGM：** {sh['bgm_mood']}")
                md_lines.append(f"**音效：** {', '.join(sh['sound_effects']) or '无'}")
                md_lines.append(f"\n**起始：** {sh['start_state']}")
                md_lines.append(f"**过程：** {sh['action_process']}")
                md_lines.append(f"**结束：** {sh['end_state']}")
                md_lines.append(f"\n**静态画面：**\n```\n{sh['visual_prompt_static']}\n```")
                md_lines.append(f"\n**运动提示词：**\n```\n{sh['visual_prompt_motion']}\n```")

            md_path = output_dir / f"第{episode:02d}集分镜.md"
            md_path.write_text("\n".join(md_lines), encoding="utf-8")

            self.log(f"saved storyboard to {output_dir}")
