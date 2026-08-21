"""Scriptwriter Agent - 按集生成剧本。接入 genre 系统。"""
import json
import re
import logging
import config
from models import Book, BookBible, EpisodeOutline, Script, CharacterProfile, CharacterStage
from core.llm import call_llm
from core import hybrid_retriever as hr
from core.production_skill import (
    build_production_skill_prompt_block,
    build_script_generation_brief_prompt_block,
    build_script_skill_execution_plan_prompt_block,
    build_script_skill_foundation_prompt_block,
    build_script_skill_foundation,
    _build_scene_execution_cards,
    load_latest_script_qa_issues,
)
from core.screenplay_compiler import compile_screenplay
from genres import get_genre
from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ScriptwriterAgent(BaseAgent):
    """按集生成剧本。根据 genre 自动切换格式。"""

    name = "scriptwriter"

    def __init__(self, book_id: int, genre: str = "short_drama"):
        super().__init__(book_id)
        self.genre = get_genre(genre)

    def run(self, episode: int) -> str:
        try:
            with self.session() as s:
                book = s.get(Book, self.book_id)
                if not book:
                    raise ValueError(f"Book {self.book_id} not found")

                bible_entry = s.query(BookBible).filter(
                    BookBible.book_id == self.book_id
                ).first()
                if not bible_entry or not bible_entry.content:
                    raise ValueError("Bible not found. Run 'bible' first.")

                ep_data = self._get_episode_data(s, episode)
                if not ep_data:
                    raise ValueError(
                        f"Episode {episode} not found in outline. Run 'outline' first."
                    )

                # Build foundation and scene execution cards
                foundation = build_script_skill_foundation(
                    book_id=self.book_id,
                    episode_outline=ep_data,
                    qa_issues=[],
                    script_content="",
                )
                exec_cards = _build_scene_execution_cards(foundation)

                if exec_cards:
                    # Scene-by-scene generation: each scene gets its own LLM call
                    logger.info(
                        "Generating %d scenes sequentially for episode %d",
                        len(exec_cards), episode,
                    )
                    raw_script_content = self._generate_scenes_sequentially(
                        exec_cards=exec_cards,
                        foundation=foundation,
                        episode_outline=ep_data,
                    )
                else:
                    # Fallback: single LLM call (when no scene cards available)
                    logger.info("No scene cards, falling back to single LLM call")
                    excerpts = self._retrieve_excerpts(s, ep_data)
                    portraits = self._build_portraits_context(s, ep_data.get("characters", []), episode)
                    adaptation_settings = self._extract_adaptation_settings(ep_data.get("title", ""))
                    prompt = self.genre.get_script_prompt(
                        bible=bible_entry.content[:config.SCENE_EXCERPT_CHARS],
                        episode_outline=json.dumps(ep_data, ensure_ascii=False, indent=2),
                        source_excerpts=excerpts,
                        episode=episode,
                        episode_title=ep_data.get("title", ""),
                        portraits=portraits[:config.PROPS_LOCS_CHARS],
                        adaptation_settings=adaptation_settings,
                    )
                    raw_script_content = call_llm(
                        prompt,
                        system=self.genre.system_prompt,
                        estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
                    )
                    raw_script_content = self._clean_script_output(raw_script_content)

                # Structural compilation: validate + enforce ending (no re-generation)
                script_content = self._compile_with_structure(
                    raw_script_content=raw_script_content,
                    book_id=self.book_id,
                    episode_outline=ep_data,
                )

                output = config.output_path(book.title, "scripts", f"第{episode:02d}集脚本.md")
                output.write_text(script_content, encoding="utf-8")

                existing = s.query(Script).filter(
                    Script.book_id == self.book_id,
                    Script.genre == self.genre.name,
                    Script.episode == episode
                ).first()
                if existing:
                    existing.content = script_content
                    existing.word_count = len(script_content)
                else:
                    s.add(Script(
                        book_id=self.book_id, genre=self.genre.name,
                        episode=episode,
                        content=script_content, word_count=len(script_content),
                        status="draft",
                    ))
                s.commit()

            return str(output)

        except Exception as e:
            logger.error("Scriptwriting failed for book %s ep %s: %s",
                         self.book_id, episode, e)
            raise

    def _get_episode_data(self, session, episode: int) -> dict | None:
        """获取单集大纲数据。"""
        ep_row = session.query(EpisodeOutline).filter(
            EpisodeOutline.book_id == self.book_id,
            EpisodeOutline.genre == self.genre.name,
            EpisodeOutline.episode == episode,
        ).first()

        if ep_row:
            return {
                "episode": ep_row.episode,
                "title": ep_row.title or "",
                "core_event": ep_row.core_event or "",
                "opening_hook": ep_row.opening_hook or "",
                "core_conflict": ep_row.core_conflict or "",
                "climax": ep_row.climax or "",
                "ending_hook": ep_row.ending_hook or "",
                "characters": (ep_row.characters or "").split(", ") if ep_row.characters else [],
                "scenes": self._parse_scenes_field(ep_row.scenes),
            }

        # Fallback: old single-blob format
        outline = session.query(EpisodeOutline).filter(
            EpisodeOutline.book_id == self.book_id,
            EpisodeOutline.genre == self.genre.name,
        ).first()
        if not outline:
            return None

        if outline.raw_content:
            episodes = self._parse_outline(outline.raw_content)
        elif outline.core_event:
            episodes = [{
                "episode": outline.episode,
                "title": outline.title or "",
                "core_event": outline.core_event or "",
                "opening_hook": outline.opening_hook or "",
                "core_conflict": outline.core_conflict or "",
                "climax": outline.climax or "",
                "ending_hook": outline.ending_hook or "",
                "characters": (outline.characters or "").split(", ") if outline.characters else [],
                "scenes": self._parse_scenes_field(outline.scenes),
            }]
        else:
            return None

        return next((e for e in episodes if e.get("episode") == episode), None)

    @staticmethod
    def _parse_scenes_field(scenes_raw: str | None) -> list:
        """Parse the scenes field which may be a Python dict repr string or comma-separated names."""
        if not scenes_raw:
            return []
        scenes_raw = scenes_raw.strip()
        # Try to parse as Python literal (list/tuple of dicts from outline generator)
        try:
            import ast
            parsed = ast.literal_eval(scenes_raw)
            if isinstance(parsed, (list, tuple)):
                # Extract location-based scene names from dict list
                result = []
                for item in parsed:
                    if isinstance(item, dict):
                        loc = str(item.get("location") or "").strip()
                        time_ = str(item.get("time") or "").strip()
                        name = f"{loc} - {time_}" if loc and time_ else loc or str(item)
                        result.append(name)
                    else:
                        result.append(str(item).strip())
                return [s for s in result if s]
        except (ValueError, SyntaxError):
            pass
        # Fallback: comma-separated
        return [name.strip() for name in scenes_raw.split(", ") if name.strip()]

    def _retrieve_excerpts(self, session, ep_data: dict) -> str:
        """检索与当前集相关的素材片段。"""
        try:
            retriever = hr.HybridRetriever(self.book_id)
            query = f"{ep_data.get('core_event', '')} {' '.join(ep_data.get('characters', []))}"
            results = retriever.search(query, n_results=5)
            excerpts = "\n---\n".join([r["document"][:800] for r in results])
            return excerpts
        except Exception as e:
            logger.warning("Source retrieval failed: %s", e)
            return ""

    def _build_portraits_context(self, session, ep_chars: list, episode: int) -> str:
        """构建角色画像上下文。"""
        if not ep_chars:
            return ""

        portraits = ""
        for char_name in ep_chars:
            try:
                stage = session.query(CharacterStage).filter(
                    CharacterStage.book_id == self.book_id,
                    CharacterStage.character_name == char_name,
                    CharacterStage.chapter_start <= episode,
                    CharacterStage.chapter_end >= episode,
                ).first()

                if stage:
                    portraits += f"\n### {char_name} ({stage.stage_name})\n"
                    portraits += f"时间线: {stage.timeline}\n"
                    portraits += f"身份: {stage.identity}\n"
                    portraits += f"年龄: {stage.age_description}\n"
                    portraits += f"脸型: {stage.face_shape}\n"
                    portraits += f"五官: {stage.facial_features}\n"
                    portraits += f"体型: {stage.body_type}\n"
                    portraits += f"穿着: {stage.signature_outfit}\n"
                    portraits += f"配饰: {stage.accessories}\n"
                    portraits += f"气质: {stage.temperament}\n"
                    portraits += f"氛围: {stage.vibe}\n"
                    portraits += f"说话风格: {stage.speech_style}\n"
                    portraits += f"体态: {stage.body_language}\n"
                else:
                    profile = session.query(CharacterProfile).filter(
                        CharacterProfile.book_id == self.book_id,
                        CharacterProfile.name == char_name,
                    ).first()
                    if profile:
                        portraits += f"\n### {char_name}\n"
                        portraits += f"身份: {profile.identity}\n"
                        portraits += f"年龄: {profile.age_range}\n"
                        portraits += f"气质: {profile.temperament}\n"
                        portraits += f"穿着: {profile.signature_outfit}\n"
                        portraits += f"说话风格: {profile.speech_style}\n"
            except Exception as e:
                logger.warning("Failed to load portrait for %s: %s", char_name, e)
                continue

        return portraits

    def _parse_outline(self, content: str) -> list:
        episodes = []
        current = None
        for line in content.split("\n"):
            if line.startswith("## 第") and "集" in line:
                if current:
                    episodes.append(current)
                m = re.search(r"第(\d+)集", line)
                ep_num = int(m.group(1)) if m else len(episodes) + 1
                title = line.split("：", 1)[-1] if "：" in line else ""
                current = {"episode": ep_num, "title": title}
            elif current and "**核心事件：**" in line:
                current["core_event"] = line.split("**核心事件：**")[-1].strip()
            elif current and "**开场钩子：**" in line:
                current["opening_hook"] = line.split("**开场钩子：**")[-1].strip()
            elif current and "**核心冲突：**" in line:
                current["core_conflict"] = line.split("**核心冲突：**")[-1].strip()
            elif current and "**反转/高潮：**" in line:
                current["climax"] = line.split("**反转/高潮：**")[-1].strip()
            elif current and "**结尾悬念：**" in line:
                current["ending_hook"] = line.split("**结尾悬念：**")[-1].strip()
            elif current and "**主要角色：**" in line:
                current["characters"] = [c.strip() for c in line.split("**主要角色：**")[-1].split(",")]
        if current:
            episodes.append(current)
        return episodes

    def _extract_adaptation_settings(self, episode_title: str) -> str:
        """从改编方案中提取角色改编设定。"""
        try:
            with self.session() as s:
                book = s.get(Book, self.book_id)
                if not book:
                    return ""
                book_title = book.title
        except Exception as e:
            logger.warning("Failed to load book for adaptation settings: %s", e)
            return ""

        adapt_path = config.output_path(book_title, f"{self.genre.name}_改编方案.md")
        if not adapt_path.exists():
            return ""

        content = adapt_path.read_text(encoding="utf-8")
        parts = []

        char_redesign = re.search(
            r'(?:##|###)\s*[三3][、.]?\s*人设改造.*?(?=(?:##|###)\s*[四4]|\Z)',
            content,
            re.DOTALL,
        )
        if char_redesign:
            text = char_redesign.group(0)[:1200]
            parts.append("【角色改编设定（改编方案中的设定优先于原始圣经）】")
            parts.append(text)

        ep_pattern = re.compile(
            r'#{2,3}\s*第\d+集《([^》]+)》\s*(.*?)(?=#{2,3}\s*第\d+集|\Z)',
            re.DOTALL,
        )
        for match in ep_pattern.finditer(content):
            title = match.group(1).strip()
            if title == episode_title:
                block = match.group(2)[:800]
                parts.append(f"【本集（{episode_title}）钩子矩阵】")
                parts.append(block)
                break

        return "\n\n".join(parts) if parts else ""

    def _compile_with_structure(
        self,
        raw_script_content: str,
        book_id: int,
        episode_outline: dict,
    ) -> str:
        """使用结构化中间层验证剧本。

        传入 raw_script_content，让编译器复用已有内容（只做约束检查+结尾保证），
        而非重新生成。
        """
        try:
            foundation = build_script_skill_foundation(
                book_id=book_id,
                episode_outline=episode_outline,
                qa_issues=[],
                script_content=raw_script_content,
            )

            fact_sheet = foundation.get("story_fact_sheet") or {}
            exec_cards = _build_scene_execution_cards(foundation)

            if not fact_sheet or not exec_cards:
                logger.info("No fact sheet or exec cards found, using raw script")
                return raw_script_content

            # 传入 raw_script_content，编译器将跳过 LLM 重新生成
            result = compile_screenplay(
                story_fact_sheet=fact_sheet,
                scene_execution_cards=exec_cards,
                foundation=foundation,
                genre_persona=self.genre.system_prompt if hasattr(self.genre, 'system_prompt') else "",
                raw_script_content=raw_script_content,
            )

            compiled_script = result.get("compiled_script") or ""
            compilation_notes = result.get("compilation_notes") or []

            logger.info("Structural compilation notes: %s", compilation_notes)

            if compiled_script and len(compiled_script) > 500:
                return compiled_script

            return raw_script_content

        except Exception as e:
            logger.warning("Structural compilation failed, using raw script: %s", e)
            return raw_script_content

    def _clean_script_output(self, raw_content: str) -> str:
        """清理LLM输出，只保留实际剧本内容。"""
        if not raw_content:
            return raw_content
        content = raw_content.strip()
        for marker in ["## 场景", "# 第", "**场景", "### 场景"]:
            idx = content.find(marker)
            if idx > 0:
                content = content[idx:]
                break

        # 移除内部笔记块：【隐藏层泄露种子：...】、【公共面具下的隐藏层...】、
        # 【信息整合】、【关键视觉证明...】、【场景收尾】等
        internal_patterns = [
            r'\*\*【隐藏层泄露种子：[^】]*】\*\*\s*',
            r'\*\*【隐藏层泄漏[^】]*】\*\*\s*',
            r'\*\*隐藏层泄露[^*]*\*\*\s*',
            r'\*\*隐藏层泄漏[^*]*\*\*\s*',
            r'\*\*【公共面具下的隐藏层[^】]*】\*\*\s*',
            r'\*\*【信息整合】\*\*[^\n]*\n(?:.*\n)*?(?=\*\*|\n##|\Z)',
            r'\*\*【关键视觉证明[^】]*】\*\*[^\n]*\n(?:.*\n)*?(?=\*\*|\n##|\Z)',
            r'\*\*【场景收尾】\*\*\s*\n(?:[^\n]+\n)*?(?=---|\n##|\Z)',
            r'# 状态提取[：:].*\n(?:[^\n]+\n)*?(?=---|\n##|\Z)',
            r'# 状态提取\s*\n(?:[^\n]+\n)*?(?=---|\n##|\Z)',
        ]
        for pat in internal_patterns:
            content = re.sub(pat, '', content)

        # 移除残留的分隔线 + 空白（场景之间的分隔线保留）
        content = re.sub(r'\n---\n\n(?=# 剧本)', '\n\n', content)

        return content.strip()

    def _validate_screenplay_format(self, content: str) -> bool:
        """验证剧本格式是否符合规范"""
        if not content:
            return False
        
        # 检查是否包含场景标记
        has_scene_marker = (
            "场景" in content or
            "场景一" in content or
            "场景1" in content or
            "**场景" in content
        )
        
        # 检查是否包含对白格式
        has_dialogue = "：" in content or ":" in content
        
        # 检查是否包含画面描述
        has_visual = "[" in content and "]" in content
        
        # 检查是否包含时间地点信息
        has_time_location = (
            "时间：" in content or
            "地点：" in content or
            "时间:" in content or
            "地点:" in content
        )
        
        # 至少满足3个条件
        conditions_met = sum([
            has_scene_marker,
            has_dialogue,
            has_visual,
            has_time_location
        ])
        
        return conditions_met >= 3

    # ------------------------------------------------------------------
    # 场景化生成（Scene-by-scene generation）
    # ------------------------------------------------------------------

    def _generate_scene(
        self,
        scene_card: dict,
        prev_state: "SceneState | None",
        character_info: str,
        hook_info: str,
        episode_meta: dict,
        is_first_scene: bool,
        is_last_scene: bool,
        retry_hint: str = "",
    ) -> tuple[str, "SceneState"]:
        """为单个场景生成剧本内容，返回 (剧本文本, 结构化结束状态)。"""
        from core.production_skill import SceneState

        parts: list[str] = []

        parts.append("你是一个专业短剧编剧。请为以下场景编写可拍摄的剧本。\n")

        # 集信息
        parts.append("## 集信息")
        parts.append(f"- 集数：第{episode_meta.get('episode', '')}集")
        parts.append(f"- 标题：{episode_meta.get('title', '')}")
        parts.append(f"- 核心冲突：{episode_meta.get('core_conflict', '')}")
        parts.append(f"- 赛道：{episode_meta.get('track_goal', '')}")
        parts.append("")

        # 角色人设
        if character_info:
            parts.append(character_info)

        # 前情提要（结构化状态）
        if is_first_scene:
            parts.append("## 前情提要\n这是第一场，没有前情。\n")
        elif prev_state and (prev_state.characters or prev_state.props):
            parts.append("## 前情提要（上一场结束时的状态——必须严格延续）")
            parts.append(prev_state.format_for_prompt())
            parts.append("")

        # 当前场景执行卡
        parts.append("## 当前场景执行卡")
        parts.append("```json")
        parts.append(json.dumps(scene_card, ensure_ascii=False, indent=2))
        parts.append("```\n")

        # 编写要求
        parts.append("## 编写要求")
        parts.append("1. 场景标题格式：## 场景X：[场景名] — [地点] — [时间]")
        parts.append("2. 必须体现 public_mask_beats 和 hidden_layer_leaks")
        parts.append("3. 必须包含 required_visual_proofs 中的所有视觉证明")
        parts.append("4. 对白格式：**角色名**对白内容。")
        parts.append("5. 至少 800 字，对白和舞台指示要详细")
        parts.append("6. 【硬约束】道具必须严格使用前情提要或场景执行卡中已列出的名称，禁止自行发明新道具名称")
        parts.append("7. 【硬约束】角色携带的物品必须与前情提要中的道具状态完全一致")
        parts.append("8. 【硬约束】角色性别必须与前情提要中的设定完全一致")
        parts.append("9. 【硬约束】角色行为必须遵守前情提要中的行为约束")
        parts.append("10. 【硬约束】不要生成内部笔记如 **【场景收尾】**、**【信息整合】**、**【关键视觉证明】** 等，这些不是剧本内容")
        parts.append("11. 【硬约束】场景必须以【场景结束】标记结尾，之前的所有内容必须是可拍摄的剧本内容")

        if is_last_scene and hook_info:
            parts.append("12. 【最重要】必须以强钩子结尾")

        # 输出格式：剧本 + 结构化状态提取
        parts.append("\n## 输出格式")
        parts.append("请按以下格式输出：")
        parts.append("1. 先输出剧本文本（Markdown 格式）")
        parts.append("2. 剧本结束后，输出状态提取块（用于下一场景的前情提要）\n")
        parts.append("状态提取块格式：")
        parts.append("```state")
        parts.append("{")
        parts.append('  "characters": [')
        parts.append('    {"name": "角色名", "gender": "男/女", "position": "位置", "emotional_state": "情绪", "props_held": ["道具1"], "behavior_guardrails": ["约束1"]}')
        parts.append("  ],")
        parts.append('  "props": [')
        parts.append('    {"name": "道具名", "owner": "持有人", "location": "位置", "physical_state": "物理状态"}')
        parts.append("  ],")
        parts.append('  "environmental_state": "环境描述",')
        parts.append('  "time_anchor": "时间描述（如：23:47）"')
        parts.append("}")
        parts.append("```\n")

        # 如果是重试，添加重试提示
        if retry_hint:
            parts.append(retry_hint)

        prompt = "\n".join(parts)

        system = self.genre.system_prompt if hasattr(self.genre, 'system_prompt') else ""
        raw = call_llm(
            prompt,
            system=system,
            estimated_tokens=4000,
        )

        # 清理剧本内容，移除内部笔记
        raw = self._clean_script_output(raw)

        # 解析输出：分离剧本和状态提取块
        script_text, extracted_state = self._parse_scene_output(raw)

        return script_text, extracted_state

    def _parse_scene_output(self, raw: str) -> tuple[str, "SceneState"]:
        """解析场景输出，分离剧本文本和结构化状态。"""
        from core.production_skill import SceneState

        if not raw:
            return "", SceneState()

        # 查找状态提取块
        state_pattern = r"```state\s*\n(.*?)\n```"
        match = re.search(state_pattern, raw, re.DOTALL)

        if match:
            state_json = match.group(1).strip()
            script_text = raw[:match.start()].strip()
            try:
                state_dict = json.loads(state_json)
                extracted_state = SceneState.from_dict(state_dict)
            except (json.JSONDecodeError, Exception):
                extracted_state = SceneState()
                script_text = raw.strip()
        else:
            # 没有状态块，整个输出作为剧本
            script_text = raw.strip()
            extracted_state = SceneState()

        return script_text, extracted_state

    def _validate_scene_completion(self, script_text: str, is_last_scene: bool) -> tuple[bool, str]:
        """校验场景是否完整（未截断）。返回 (是否完整, 失败原因)。"""
        if not script_text:
            return False, "场景内容为空"
        
        # 检查是否有场景标题
        has_scene_header = bool(re.search(r"##\s*场景", script_text))
        if not has_scene_header:
            return False, "缺少场景标题"
        
        # 检查是否有对白
        has_dialogue = "**" in script_text and "：" in script_text
        if not has_dialogue:
            return False, "缺少对白内容"
        
        # 检查对白是否完整（没有未闭合的引号）
        # 统计中文引号数量
        left_quotes = script_text.count("「") + script_text.count("『") + script_text.count("（")
        right_quotes = script_text.count("」") + script_text.count("』") + script_text.count("）")
        quotes_balanced = abs(left_quotes - right_quotes) <= 2  # 允许少量不平衡
        if not quotes_balanced:
            return False, f"引号不平衡（左{left_quotes}个，右{right_quotes}个）"
        
        # 检查最小字数（至少500字）
        min_length_ok = len(script_text) >= 500
        if not min_length_ok:
            return False, f"字数不足（{len(script_text)}字，需要至少500字）"
        
        # 检查是否有截断的句子（以省略号或不完整句子结尾）
        last_line = script_text.rstrip().split("\n")[-1] if script_text.rstrip() else ""
        # 截断检测：最后一行以逗号、省略号结尾，或者太短
        is_truncated = bool(re.search(r"[，、…]$", last_line)) or (len(last_line.strip()) < 10 and not last_line.strip().endswith(("。", "！", "？", "」", "』", "）", "】")))
        if is_truncated:
            return False, f"场景结尾被截断（最后一行：{last_line[:50]}...）"
        
        # 检查是否有结尾标记
        has_ending = bool(re.search(r"（.*结束.*）|\[画面渐隐\]|（场景结束）|【.*结束.*】|\*?\*?\[场景结束\]", script_text))
        
        # 非最后一场只需有标题和对白；最后一场需要有结尾标记
        if is_last_scene and not has_ending:
            return False, "最后一场缺少结尾标记"
        
        return True, ""

    def _continue_scene_ending(
        self,
        script_text: str,
        scene_card: dict,
        character_info: str,
        is_last_scene: bool,
    ) -> str:
        """续写被截断的场景结尾。"""
        if not script_text:
            return script_text
        
        # 获取最后500个字符作为上下文
        context = script_text[-500:] if len(script_text) > 500 else script_text
        
        parts = [
            "你是一个专业短剧编剧。以下场景的结尾被截断了，请续写完整的结尾。",
            "",
            "## 已生成的场景内容（最后部分）",
            context,
            "",
            "## 续写要求",
            "1. 请从上面内容的末尾继续编写，不要重复已有内容",
            "2. 必须补全被截断的对白或句子",
            "3. 场景必须以【场景结束】标记结尾",
            "4. 如果是最后一场，必须以强钩子结尾",
            "5. 续写字数：300-500字",
        ]
        
        if is_last_scene:
            parts.append("6. 【最重要】必须以震撼性的钩子结尾，让观众迫不及待想看下一集")
        
        prompt = "\n".join(parts)
        
        system = self.genre.system_prompt if hasattr(self.genre, 'system_prompt') else ""
        raw = call_llm(
            prompt,
            system=system,
            estimated_tokens=2000,
        )
        
        # 将续写内容追加到原场景
        continuation = raw.strip()
        if continuation:
            # 清理续写内容
            continuation = self._clean_script_output(continuation)
            # 移除续写内容中可能的重复标题
            continuation = re.sub(r"^#.*\n*", "", continuation)
            # 移除续写开头的分隔线
            continuation = re.sub(r"^---\n*", "", continuation)
            return script_text + "\n\n" + continuation
        
        return script_text

    def _generate_scenes_sequentially(
        self,
        exec_cards: list[dict],
        foundation: dict,
        episode_outline: dict,
    ) -> str:
        """逐场景生成剧本，每个场景独立 LLM 调用，使用结构化状态传递。"""
        from core.production_skill import SceneState
        from core.screenplay_compiler import (
            _build_character_info_block,
            _build_hook_info_block,
        )

        fact_sheet = foundation.get("story_fact_sheet") or {}
        episode_goal = foundation.get("episode_goal_card") or {}

        character_info = _build_character_info_block(fact_sheet)
        hook_info = _build_hook_info_block(fact_sheet)

        scenes: list[str] = []
        current_state: SceneState | None = None
        total = len(exec_cards)

        for i, card in enumerate(exec_cards):
            is_first = i == 0
            is_last = i == total - 1

            script_text, extracted_state = self._generate_scene(
                scene_card=card,
                prev_state=current_state,
                character_info=character_info,
                hook_info=hook_info,
                episode_meta=episode_goal,
                is_first_scene=is_first,
                is_last_scene=is_last,
            )

            # 校验场景完整性，不完整则续写结尾
            is_complete, fail_reason = self._validate_scene_completion(script_text, is_last)
            if not is_complete:
                logger.warning(f"场景 {i+1} 生成不完整（{fail_reason}），尝试续写结尾...")
                script_text = self._continue_scene_ending(
                    script_text=script_text,
                    scene_card=card,
                    character_info=character_info,
                    is_last_scene=is_last,
                )
                # 重新提取状态
                _, extracted_state = self._parse_scene_output(script_text)
                
                # 再次校验
                is_complete, fail_reason = self._validate_scene_completion(script_text, is_last)
                if not is_complete:
                    logger.warning(f"场景 {i+1} 续写后仍不完整（{fail_reason}），尝试完整重写...")
                    retry_suffix = f"\n\n【重试要求】上一次生成失败原因：{fail_reason}。请确保：\n"
                    retry_suffix += "1. 场景必须有完整的结尾（不被截断）\n"
                    retry_suffix += "2. 所有对白必须完整，不以逗号或省略号结尾\n"
                    retry_suffix += "3. 场景必须以【场景结束】标记结尾\n"
                    retry_suffix += "4. 字数不少于500字"
                    
                    script_text, extracted_state = self._generate_scene(
                        scene_card=card,
                        prev_state=current_state,
                        character_info=character_info,
                        hook_info=hook_info,
                        episode_meta=episode_goal,
                        is_first_scene=is_first,
                        is_last_scene=is_last,
                        retry_hint=retry_suffix,
                    )

            scenes.append(script_text)
            # 将本场的结束状态传递给下一场
            current_state = extracted_state

        header = f"# 第{episode_outline.get('episode', '')}集 {episode_outline.get('title', '')}\n\n"
        separator = "\n\n---\n\n"
        return header + separator.join(scenes)
