"""Rewrite agent with structured output validation and screenplay fallback."""

from __future__ import annotations

import json
import logging
import re
from typing import Iterable

import config
from agents.base import BaseAgent
from core.llm import call_llm
from core.repair import (
    StructuralRepairEngine,
    build_structural_repair_context,
    validate_generated_script,
)
from core.production_skill import (
    build_script_issue_rewrite_directive,
    build_production_skill_prompt_block,
    build_script_generation_brief_prompt_block,
    build_script_skill_execution_plan_prompt_block,
    build_script_skill_foundation_prompt_block,
    build_script_skill_repair_packet_prompt_block,
    load_latest_script_qa_issues,
)
from core.structured_output import parse_json_object, strip_code_fences, write_debug_output
from models import Book, EpisodeOutline, Script

logger = logging.getLogger(__name__)


class RewriteAgent(BaseAgent):
    """Rewrite an existing script while preserving a structured output contract."""

    name = "rewrite"
    SCREENPLAY_META_LABELS = (
        "场景目的",
        "场景冲突",
        "信息增量",
        "情绪增量",
        "场景出口钩子",
    )
    SCREENPLAY_ANNOTATION_LABELS = (
        "情绪点",
        "疑点/反转点",
        "疑点",
        "反转点",
    )
    AUXILIARY_SECTION_TITLES = (
        "剧集设定",
        "集级大纲",
        "角色状态卡",
        "角色卡",
        "人物状态卡",
        "关键道具台账",
        "关键资产表",
        "资产台账",
        "场景分镜草案",
        "分镜草案",
        "分镜细化",
        "信息钩子",
        "证据链说明",
        "总体节奏与合规自查",
        "情绪点标注",
        "疑点/反转点标注",
        "疑点标注",
        "反转点标注",
        "下集预告弹层",
    )

    META_FRAGMENTS = [
        "Need ",
        "Let's ",
        "analysis",
        "The user wants me",
        "Let me analyze",
        "Let me think",
        "修复说明",
        "问题：",
        "草稿",
        "方案：",
        "现在我们",
        "注意：",
        "这样应该够了",
        "下面开始构思",
        "现在开始起草完整剧本",
        "让我们仔细分析",
        "用户要求我",
        "我们需要输出",
        "Output Format Rules",
        "让我分析",
        "实际上",
        "但等等",
        "回顾一下",
    ]

    def _load_episode_outline(self, session, episode: int) -> dict:
        row = session.query(EpisodeOutline).filter(
            EpisodeOutline.book_id == self.book_id,
            EpisodeOutline.episode == episode,
        ).order_by(EpisodeOutline.id.desc()).first()
        if not row:
            return {}
        return {
            "episode": row.episode,
            "title": row.title or "",
            "core_event": row.core_event or "",
            "opening_hook": row.opening_hook or "",
            "core_conflict": row.core_conflict or "",
            "climax": row.climax or "",
            "ending_hook": row.ending_hook or "",
            "characters": (row.characters or "").split(", ") if row.characters else [],
            "scenes": (row.scenes or "").split(", ") if row.scenes else [],
        }

    def _load_expected_scene_names(self) -> list[str]:
        extracted: list[str] = []
        script_content = str(getattr(self, "_current_script_content", "") or "")
        scene_patterns = [
            r"^##\s*场景[^\[\n]*\[(.*?)\]",
            r"^\*\*场景[^\[\n]*\[(.*?)\]\*\*",
            r"^##\s*Scene\s*[0-9]+[^\[\n]*\[(.*?)\]",
            r"^\*\*Scene\s*[0-9]+[^\[\n]*\[(.*?)\]\*\*",
        ]
        for pattern in scene_patterns:
            for match in re.findall(pattern, script_content, flags=re.MULTILINE):
                name = str(match).strip()
                if name and name not in extracted:
                    extracted.append(name)
        if extracted:
            return extracted

        names = [
            str(item).strip()
            for item in (self._episode_outline.get("scenes") or [])
            if str(item).strip()
        ]
        if names:
            return names
        return ["scene-1", "scene-2"]

    def _build_rewrite_prompt(
        self,
        script_content: str,
        skill_block: str,
        foundation_block: str,
        generation_brief_block: str,
        execution_plan_block: str,
        repair_packet_block: str,
        *,
        previous_invalid_output: str = "",
        previous_error: str = "",
    ) -> str:
        retry_notice = ""
        if previous_invalid_output.strip():
            retry_notice = (
                "## Retry Notice\n"
                "Your previous response did not satisfy the JSON contract.\n"
                f"Observed issue: {previous_error or 'invalid structured output'}\n"
                "Return valid JSON only this time. Do not explain your reasoning.\n"
                "Do not repeat placeholders, examples, or analysis outside JSON.\n\n"
            )
        # Get structural validation from repair packet
        structural_validation_prompt = ""
        if hasattr(self, '_structural_validation_prompt'):
            structural_validation_prompt = self._structural_validation_prompt
        
        return (
            f"{skill_block}\n\n"
            f"{foundation_block}\n\n"
            f"{generation_brief_block}\n\n"
            f"{execution_plan_block}\n\n"
            f"{repair_packet_block}\n\n"
            f"{structural_validation_prompt}\n\n"
            f"{retry_notice}"
            "## Rewrite Task\n"
            "Repair the current episode script under Production Skill constraints.\n"
            "Treat `Script Generation Brief` as the primary structural map for character layers, scene goals, evidence flow, prop movement, and hook delta.\n"
            "Treat `story_fact_sheet` as the fact-locked source of truth for public persona, hidden layer, core prop uniqueness, helper motive, spatial mechanics, and hook delta.\n"
            "Treat each `scene_compilation_card` as a required scene-by-scene construction card. Resolve the cards in order instead of globally improvising a replacement episode shape.\n"
            "Treat each `scene_execution_card` as the execution-level contract for opening state, required visual proofs, closing state, and handoff into the next scene.\n"
            "Treat `prop_timeline_brief` as the scene-by-scene ledger for where key props begin, where they should end, and which transfer beats must be visible.\n"
            "Treat `structure_focus` and `stage_repair_priorities` as the repair-order contract: fix the dominant stage first, then move to the next stage instead of mixing every symptom at once.\n"
            "Treat `stage_repair_agenda` as the ordered repair worklist. Finish each stage's ordered actions before drifting into later-stage polish.\n"
            "Treat `scene_repair_agenda` as the per-scene repair contract. For each scene, land the listed stage tasks, visual proofs, action-feasibility fixes, and hook delta in the screenplay body.\n"
            "Apply repairs in repair-priority order.\n"
            "Resolve every issue_rewrite_directive inside the screenplay itself.\n"
            "Keep the episode core event, conflict, and valid continuity unless a repair brief requires adjustment.\n"
            "Return only valid JSON. No markdown fences. No commentary outside JSON.\n"
            "Use actual rewritten content, not placeholders or ellipses.\n\n"
            "## Rewrite Quality Floor\n"
            "- `rewritten_script` must be a complete episode draft, not a stub.\n"
            "- Preserve or improve scene structure; do not collapse the episode into a summary.\n"
            f"- Preserve the existing scene count and scene order unless a repair directive explicitly requires a split or merge. Expected scene sequence: {', '.join(self._expected_scene_names)}.\n"
            "- Keep the same scene boundary logic whenever possible; do not silently move a beat from one location block to another just to make a line fit.\n"
            "- Repair scene by scene. For each scene, satisfy the current scene card's driver, visual anchor, new evidence goal, clue reuse goal, and exit delta before moving on.\n"
            "- Repair contradictions with the smallest consistent adjustment; do not invent new chronology facts, page numbers, prop counts, or backstory details unless the script visibly stages them.\n"
            "- Every repair priority must show up inside the rewritten script, not only in diagnosis.\n"
            "- Keep dialogue and behavior aligned with each character's visible-state guardrails and speech-style anchor.\n"
            "- If character canon defines a habitual phrase, draggy cadence, excuse pattern, or ritual opener, let at least one early line preserve that audible signature before deeper intent surfaces.\n"
            "- If bound portraits, character sheets, or asset canon define a role's public persona, keep the screenplay inside that persona unless the script explicitly stages a revised canon, a disguise, or a hidden-layer reveal.\n"
            "- If a character's bound public persona is lazy, perfunctory, timid, evasive, or soft, keep that quality in their line rhythm, hesitation, delegation pattern, and movement tempo instead of jumping straight into crisp command behavior.\n"
            "- When hidden competence exists under a soft or lazy mask, let it surface through what the character quietly notices, delays, withholds, or pointedly skips before it surfaces in overtly capable action.\n"
            "- If a character appears in a new location or with a newly visible prop, add a visible transition or acquisition beat.\n"
            "- If a scene cut changes restraint, custody, or concealment state, show the release, escape, or handoff beat before the next scene starts.\n"
            "- If characters announce a custody destination such as a storehouse, shed, cell, or back room, keep the next scene in that place or show the reroute explicitly.\n"
            "- Keep relative time phrases consistent with staged action and flashbacks; phrases like before entering, last night, at dusk, and this morning cannot contradict the shown timeline.\n"
            "- Keep body-action logic physically playable; tied, pinned, injured, or half-hidden characters cannot perform impossible motions unless the script first shows the release or workaround.\n"
            "- If a character is transferred from one restraint anchor or custody setup to another within the same scene, show the unhook, drag, turn, or reposition beat before the new binding state appears.\n"
            "- If a lazy, evasive, timid, or perfunctory character must search, detain, escort, or enforce rules, keep that action inside the same persona through complaint, excuse-making, borrowed authority, half-hearted handling, or efficiency aimed at ending trouble quickly.\n"
            "- When a hidden layer surfaces, show the trigger on screen before the stronger line or reveal lands.\n"
            "- Do not let a major deduction appear from nowhere; attach each conclusion to an on-screen source, prior action, flashback beat, or visible comparison.\n"
            "- When dialogue names a decisive clue, theft, missing item, or fresh damage for the first time, pair that line with the visual anchor in the same beat or show the anchor earlier.\n"
            "- If a plot-relevant sound cue appears, pair it with a visible source, silhouette, tool edge, or body movement so the clue is not carried by audio alone.\n"
            "- Keep visible surface evidence separate from hidden underlayer inference; if a mark is still under wax, cloth, mud, paper, or another cover, only the surface trace or seal condition can be described until the cover is opened.\n"
            "- If a character witnesses blood, a body trace, or a major crime clue but stays silent, state the reason on screen as fear, strategy, infiltration, lack of proof, or self-protection.\n"
            "- If a character uses a hidden method, ritual, code, or evidence-reveal technique, show where that knowledge came from before or during the reveal.\n"
            "- If a later reveal depends on a hidden inscription, carved stroke, sealed label, or covered mark, show earlier when that mark was written, cut, or sealed under the cover.\n"
            "- If a later reveal depends on a tiny physical clue such as a scratch, wax nick, pressure dent, missing corner, or thread color, show that seed detail in the active scene image now instead of leaving it only in summary notes.\n"
            "- If a clue stays concealed under wax, cloth, mud, paper, or another cover, still give the audience one memorable visible abnormality that marks it as suspicious before the actual reveal.\n"
            "- If a clue surface or seam was already shown earlier, later handling must add a new layer of information instead of replaying the same discovery as brand new.\n"
            "- If another character searches the protagonist, define what layer gets searched and where any surviving hidden evidence is stashed.\n"
            "- If a searcher notices an abnormal detail but does not pursue it, stage the interruption, concealment motive, or deliberate withdrawal in the same beat.\n"
            "- If a hidden helper tool, wax cloth, copper wire, note, or stash appears from clothes, bedding, or a sleeve fold, establish earlier when and why it was planted there.\n"
            "- If multiple hidden helper items belong to the same concealed kit, stage that kit together in the same prep or flashback beat instead of introducing each item separately without setup.\n"
            "- Keep weather, light source, and visibility coherent across the scene; rain, moonlight, lamp glow, darkness, and wet surfaces must describe one compatible environment state.\n"
            "- If secondary characters escalate from suspicion to confiscation, restraint, beating, or surveillance, show the concrete trigger in frame: a recognized object, prior grudge, contradictory answer, marked prop, or visible fear reaction.\n"
            "- If one character accuses or detains another for a concrete crime, place at least one visible accusation trigger in frame instead of relying on generalized suspicion alone.\n"
            "- Dialogue about having checked, solved, cleared, or released someone must match the actual action state on screen; do not announce closure while custody or suspicion is still escalating.\n"
            "- Keep high-value props on one coherent timeline across scenes; avoid contradictory locations or states for the same object.\n"
            "- If a prop is explicitly placed back into view, stored, or left on a surface, do not show the same character immediately discovering or re-taking it again without one visible intervening reason, return beat, or changed objective.\n"
            "- If a prop found in a room, chest, or storage place explains an earlier action, show who took it from there and how that source chain connects back to the earlier beat.\n"
            "- Once a prop has been pocketed, wrapped, hidden, or moved, later reuse must come from that latest state and location, not from the original place.\n"
            "- If a prop was discarded, dropped into water, kicked aside, or confiscated earlier, later reuse must show the recovery or hidden retrieval beat on screen.\n"
            "- If a character reuses a prop to fake an earlier visible state, such as re-looping a rope or re-hanging a token, show the restaging action explicitly.\n"
            "- If one character notices a hidden hard object, seam bulge, missing weight, or suspicious tool once and then checks it again later, the second check must be justified by a new trigger, interruption ending, or higher-stakes reinspection purpose.\n"
            "- If a location is searched earlier but yields a later discovery, stage the gating reason for the miss: darkness, angle, obstruction, hidden compartment, water level, or interruption.\n"
            "- If one document, page, or clue is both delivered earlier and revealed later, show the split clearly as a copy, torn page, extracted fragment, duplicate bundle, or prior removal beat.\n"
            "- If a striking clue image appears, either reuse it later in suspicion or payoff logic, or cut it; do not leave strong visual evidence as a one-off ornament.\n"
            "- Keep page numbers, counts, labels, and small evidence details stable across the whole episode.\n"
            "- Dialogue cannot claim stronger certainty than the shown evidence supports; if the character inferred it, phrase it as inference rather than eyewitness fact.\n"
            "- If a clue could point to both the obvious suspect and a hidden suspect, add the distinguishing physical feature that keeps the inference sharp.\n"
            "- Shared material alone is not enough for a decisive clue match; if two fibers, knots, stains, or marks are compared, give at least one unique feature such as placement pattern, cut angle, wrap style, residue, or source-limited usage.\n"
            "- Do not redefine the nature of the same clue later unless the earlier statement was clearly marked as uncertainty, bluff, or deception.\n"
            "- If a character is bluffing or misleading, give the audience an on-screen cue or a later reveal that makes the deception legible.\n"
            "- Avoid overloading one scene with too many unrelated major reveals in one uninterrupted speech.\n"
            "- Before a character commits to the next risky action, state the concrete objective on screen.\n"
            "- If a character repeatedly risks exposure to move, plant, retrieve, or re-stage the same clue, state the concrete objective behind that risk so the audience can tell plan from sloppiness.\n"
            "- Compress explanatory dialogue into object handling plus one short line whenever the camera can do the explanation.\n"
            "- Replace abstract inner narration such as remembering, deciding, suspecting, or filing something away with visible micro-action the camera can show.\n"
            "- If the conflict depends on an off-screen theft, missing item, injury, or alarm event, add one visible aftermath anchor in frame so the event is not carried by dialogue alone.\n"
            "- If a flashback interrupts active danger, keep the present-tense pressure alive across the cut with a sound carry, image echo, ticking action, or immediate return trigger.\n"
            "- If a flashback lands inside active danger, compress it into short inserts or move it to the first safe beat instead of draining the live threat.\n"
            "- If a suspense image or shadow motif repeats later in the episode, the later beat must add new information, threat, or identification value.\n"
            "- The ending hook must add a fresh delta beyond what the audience already knew: a new suspect direction, timed danger, prop change, access point, or consequence, not just a restatement of an existing clue.\n"
            "- Escape or lock-breaking beats must match the shown hardware geometry; if a hook, wire, or loop opens the door, the frame must first establish the exact reachable latch path.\n"
            "- Calibrate hidden-identity hints to the intended certainty: keep them non-exclusive if the watcher should stay ambiguous, or add a second anchor such as shoe shape, sleeve edge, gait, tool, or stance if the audience should lean toward one identity.\n"
            "- The ending hook should still read without the final line; add a visible prop gesture, silhouette shift, body action, or object change so the image lands before dialogue.\n\n"
            "## Required JSON Output\n"
            "{\n"
            '  "diagnosis": {\n'
            '    "summary": "actual diagnosis summary",\n'
            '    "applied_rule_families": ["actual_rule_family"],\n'
            '    "remaining_risks": ["actual_remaining_risk"]\n'
            "  },\n"
            '  "rewritten_script": "actual full rewritten episode script text",\n'
            '  "change_summary": ["actual change 1", "actual change 2"]\n'
            "}\n\n"
            "## Current Episode Script\n"
            f"{script_content[:5000]}"
        )

    def _build_scene_scaffold(self) -> str:
        numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        lines: list[str] = []
        for index, name in enumerate(self._expected_scene_names, start=1):
            numeral = numerals[index - 1] if index <= len(numerals) else str(index)
            lines.extend(
                [
                    f"## 场景{numeral} [{name}]",
                    "画面：",
                    "角色甲：台词",
                    "角色乙：台词",
                    "特写：",
                    "",
                ]
            )
        return "\n".join(lines).strip()

    def _build_script_only_fallback_prompt(self) -> str:
        salvage_hint_block = ""
        if getattr(self, "_fallback_salvage_hints", ""):
            salvage_hint_block = (
                "## Salvaged Repair Hints\n"
                f"{self._fallback_salvage_hints.strip()}\n\n"
            )
        return (
            f"{self._skill_block}\n\n"
            f"{self._foundation_block}\n\n"
            f"{self._execution_plan_block}\n\n"
            f"{self._repair_packet_block}\n\n"
            f"{salvage_hint_block}"
            "## Fallback Rewrite Task\n"
            "The structured JSON path failed.\n"
            "Return only the final rewritten episode script text.\n"
            "Do not return JSON. Do not include diagnosis. Do not explain your reasoning.\n"
            "Do not include planning notes, checks, comments, options, or alternate versions.\n\n"
            "Resolve every issue_rewrite_directive from the repair packet inside the screenplay body.\n"
            "Follow `stage_repair_agenda` in order and let `scene_repair_agenda` decide what each scene must physically show.\n\n"
            "## Screenplay Rules\n"
            "- The first line must be a formal scene header such as `## 场景一 [地点·时间]`.\n"
            "- Every scene must contain visible action, playable dialogue, and at least one prop or evidence beat in frame.\n"
            "- Repair contradictions with the smallest consistent adjustment; do not invent new chronology facts, page numbers, prop counts, or backstory details unless the script visibly stages them.\n"
            "- Dialogue lines must use the `角色：台词` format.\n"
            "- Use `画面：` or `特写：` beats to make important evidence visible on screen.\n"
            "- The ending scene must land a next-episode hook instead of ending flat.\n"
            "- Include the full set of planned scenes. Do not stop mid-episode.\n"
            "- Keep each character's dialogue and body language aligned with the visible-state guardrails from Script Skill Foundation.\n"
            "- If character canon defines a habitual phrase, draggy cadence, excuse pattern, or ritual opener, let at least one early line preserve that audible signature before deeper intent surfaces.\n"
            "- If bound portraits, character sheets, or asset canon define a role's public persona, keep the screenplay inside that persona unless the script explicitly stages a revised canon, a disguise, or a hidden-layer reveal.\n"
            "- If a public persona is lazy, perfunctory, timid, evasive, or soft, preserve that texture in wording and tempo instead of turning the character into a brisk commander without a staged trigger.\n"
            "- If a character suddenly changes tone, reveals hidden knowledge, or appears with a new prop, first show the visible trigger or transition beat.\n"
            "- If a scene cut changes restraint, custody, or concealment state, show the release, escape, or handoff beat before the next scene starts.\n"
            "- If characters announce a custody destination such as a storehouse, shed, cell, or back room, keep the next scene in that place or show the reroute explicitly.\n"
            "- Keep relative time phrases consistent with staged action and flashbacks; phrases like before entering, last night, at dusk, and this morning cannot contradict the shown timeline.\n"
            "- Keep body-action logic physically playable; tied, pinned, injured, or half-hidden characters cannot perform impossible motions unless the script first shows the release or workaround.\n"
            "- If a character is transferred from one restraint anchor or custody setup to another within the same scene, show the unhook, drag, turn, or reposition beat before the new binding state appears.\n"
            "- If a lazy, evasive, timid, or perfunctory character must search, detain, escort, or enforce rules, keep that action inside the same persona through complaint, excuse-making, borrowed authority, half-hearted handling, or efficiency aimed at ending trouble quickly.\n"
            "- Do not let props, evidence, or scene geography teleport between scenes without on-screen handoff.\n"
            "- Every major inference must be supported by a visible source, comparison, flashback beat, or prior investigation action.\n"
            "- When dialogue names a decisive clue, theft, missing item, or fresh damage for the first time, pair that line with the visual anchor in the same beat or show the anchor earlier.\n"
            "- If a plot-relevant sound cue appears, pair it with a visible source, silhouette, tool edge, or body movement so the clue is not carried by audio alone.\n"
            "- Keep visible surface evidence separate from hidden underlayer inference; if a mark is still under wax, cloth, mud, paper, or another cover, only the surface trace or seal condition can be described until the cover is opened.\n"
            "- If a character witnesses blood, a body trace, or a major crime clue but stays silent, state the reason on screen as fear, strategy, infiltration, lack of proof, or self-protection.\n"
            "- If a character uses a hidden method, ritual, code, or evidence-reveal technique, show where that knowledge came from before or during the reveal.\n"
            "- If a later reveal depends on a hidden inscription, carved stroke, sealed label, or covered mark, show earlier when that mark was written, cut, or sealed under the cover.\n"
            "- If a later reveal depends on a tiny physical clue such as a scratch, wax nick, pressure dent, missing corner, or thread color, show that seed detail in the active scene image now instead of leaving it only in summary notes.\n"
            "- If a clue stays concealed under wax, cloth, mud, paper, or another cover, still give the audience one memorable visible abnormality that marks it as suspicious before the actual reveal.\n"
            "- If a clue surface or seam was already shown earlier, later handling must add a new layer of information instead of replaying the same discovery as brand new.\n"
            "- If another character searches the protagonist, define what layer gets searched and where any surviving hidden evidence is stashed.\n"
            "- If a searcher notices an abnormal detail but does not pursue it, stage the interruption, concealment motive, or deliberate withdrawal in the same beat.\n"
            "- If a hidden helper tool, wax cloth, copper wire, note, or stash appears from clothes, bedding, or a sleeve fold, establish earlier when and why it was planted there.\n"
            "- If multiple hidden helper items belong to the same concealed kit, stage that kit together in the same prep or flashback beat instead of introducing each item separately without setup.\n"
            "- Keep weather, light source, and visibility coherent across the scene; rain, moonlight, lamp glow, darkness, and wet surfaces must describe one compatible environment state.\n"
            "- If secondary characters escalate from suspicion to confiscation, restraint, beating, or surveillance, show the concrete trigger in frame: a recognized object, prior grudge, contradictory answer, marked prop, or visible fear reaction.\n"
            "- If one character accuses or detains another for a concrete crime, place at least one visible accusation trigger in frame instead of relying on generalized suspicion alone.\n"
            "- Dialogue about having checked, solved, cleared, or released someone must match the actual action state on screen; do not announce closure while custody or suspicion is still escalating.\n"
            "- Keep high-value props on one consistent timeline across scenes.\n"
            "- If a prop found in a room, chest, or storage place explains an earlier action, show who took it from there and how that source chain connects back to the earlier beat.\n"
            "- Once a prop has been pocketed, wrapped, hidden, or moved, later reuse must come from that latest state and location, not from the original place.\n"
            "- If a prop was discarded, dropped into water, kicked aside, or confiscated earlier, later reuse must show the recovery or hidden retrieval beat on screen.\n"
            "- If a character reuses a prop to fake an earlier visible state, such as re-looping a rope or re-hanging a token, show the restaging action explicitly.\n"
            "- If a location is searched earlier but yields a later discovery, stage the gating reason for the miss: darkness, angle, obstruction, hidden compartment, water level, or interruption.\n"
            "- If one document, page, or clue is both delivered earlier and revealed later, show the split clearly as a copy, torn page, extracted fragment, duplicate bundle, or prior removal beat.\n"
            "- If a striking clue image appears, either reuse it later in suspicion or payoff logic, or cut it; do not leave strong visual evidence as a one-off ornament.\n"
            "- Keep page numbers, counts, labels, and small evidence details stable across the whole episode.\n"
            "- Dialogue cannot claim stronger certainty than the shown evidence supports; if the character inferred it, phrase it as inference rather than eyewitness fact.\n"
            "- If a clue could point to both the obvious suspect and a hidden suspect, add the distinguishing physical feature that keeps the inference sharp.\n"
            "- Do not label the same clue as different things across scenes unless the earlier label was intentionally deceptive and later revealed as such.\n"
            "- If a character bluffs, lies, or tests another character, make that bluff legible in action, expression, or later payoff.\n"
            "- Split or stage revelations so one scene does not dump too many unrelated twists in a single uninterrupted run.\n"
            "- Before a character commits to the next risky action, state the concrete objective on screen.\n"
            "- Compress explanatory dialogue into object handling plus one short line whenever the camera can do the explanation.\n"
            "- Replace abstract inner narration such as remembering, deciding, suspecting, or filing something away with visible micro-action the camera can show.\n"
            "- If the conflict depends on an off-screen theft, missing item, injury, or alarm event, add one visible aftermath anchor in frame so the event is not carried by dialogue alone.\n"
            "- If a flashback interrupts active danger, keep the present-tense pressure alive across the cut with a sound carry, image echo, ticking action, or immediate return trigger.\n"
            "- If a flashback lands inside active danger, compress it into short inserts or move it to the first safe beat instead of draining the live threat.\n"
            "- If a suspense image or shadow motif repeats later in the episode, the later beat must add new information, threat, or identification value.\n"
            "- The ending hook must add a fresh delta beyond what the audience already knew: a new suspect direction, timed danger, prop change, access point, or consequence, not just a restatement of an existing clue.\n"
            "- Calibrate hidden-identity hints to the intended certainty: keep them non-exclusive if the watcher should stay ambiguous, or add a second anchor such as shoe shape, sleeve edge, gait, tool, or stance if the audience should lean toward one identity.\n"
            "- The final beat must end on a visible hook image, not only on an abstract line or title card.\n"
            "- The ending hook should still read without the final line; add a visible prop gesture, silhouette shift, body action, or object change so the image lands before dialogue.\n"
            "- Never output words like `Need`, `Let's`, `analysis`, `修复说明`, `问题`, `草稿`, or `方案`.\n\n"
            "## Required Scene Scaffold\n"
            f"{self._build_scene_scaffold()}\n\n"
            "## Current Episode Script\n"
            f"{self._current_script_content[:5000]}"
        )

    def _build_script_normalization_prompt(self, invalid_output: str) -> str:
        return (
            f"{self._skill_block}\n\n"
            f"{self._foundation_block}\n\n"
            f"{self._execution_plan_block}\n\n"
            f"{self._repair_packet_block}\n\n"
            "## Screenplay Normalization Task\n"
            "You are given a failed rewrite attempt that may contain analysis, partial screenplay, or mixed notes.\n"
            "Convert it into one final rewritten episode screenplay only.\n"
            "Do not output JSON. Do not explain. Do not include planning notes.\n"
            "The first line must be a formal scene header.\n"
            "Resolve every issue_rewrite_directive from the repair packet while normalizing the failed attempt.\n"
            "Keep all planned scenes and preserve only claims supported by the source attempt.\n\n"
            "## Required Scene Scaffold\n"
            f"{self._build_scene_scaffold()}\n\n"
            "## Failed Attempt Source\n"
            f"{str(invalid_output or '')[:7000]}"
        )

    def _build_compiler_rebuild_prompt(self) -> str:
        return (
            f"{self._skill_block}\n\n"
            f"{self._foundation_block}\n\n"
            f"{self._execution_plan_block}\n\n"
            f"{self._repair_packet_block}\n\n"
            "## Compiler Rebuild Task\n"
            "Recompile the episode from the Production Skill structure instead of patching the current draft line by line.\n"
            "Use `story_fact_sheet`, `stage_repair_agenda`, and `scene_repair_agenda` as the primary source of truth.\n"
            "Only preserve a beat from the current draft if it is consistent with the fact sheet, the scene agenda, and the active repair directives.\n"
            "If the current draft contains stale beats that conflict with the repair agenda, replace them rather than soft-editing around them.\n"
            "Return only the final screenplay text. Do not return JSON. Do not explain. Do not include notes or alternate versions.\n"
            "The first line must be the first scene header exactly.\n"
            "Write the complete episode in screenplay form with visible action, dialogue, and evidence beats.\n\n"
            "## Exact Scene Scaffold\n"
            f"{self._build_scene_scaffold()}\n\n"
            "## Current Episode Script\n"
            f"{str(getattr(self, '_current_script_content', '') or '')[:3200]}"
        )

    def _build_compact_json_fallback_prompt(self) -> str:
        scene_sequence = ", ".join(getattr(self, "_expected_scene_names", []) or ["scene-1", "scene-2"])
        issue_focus_block = self._build_compact_issue_focus_block()
        current_script_excerpt = str(getattr(self, "_current_script_content", "") or "")[:2200]
        salvage_hint_block = ""
        if getattr(self, "_fallback_salvage_hints", ""):
            salvage_hint_block = (
                "## Salvaged Repair Hints\n"
                f"{self._fallback_salvage_hints.strip()}\n\n"
            )
        return (
            "## Compact Rewrite JSON Recovery\n"
            "Return valid JSON only. Do not include analysis, notes, drafts, or markdown fences.\n"
            "The first non-whitespace character of your response must be `{` and the last character must be `}`.\n"
            "Do not restate the task. Do not explain the issues. Do not think step by step in the answer.\n"
            "Repair the episode screenplay while preserving the planned scene order.\n"
            f"Expected scene sequence: {scene_sequence}\n\n"
            "## Critical Rules\n"
            "- Keep screenplay form with full scene headers, visual beats, and dialogue.\n"
            "- Resolve continuity, clue provenance, persona drift, and hook weakness inside the rewritten scenes.\n"
            "- If diagnosis wording is uncertain, keep it short and prioritize a complete `rewritten_script`.\n"
            "- Do not output any text before or after the JSON object.\n\n"
            "## Scene Scaffold\n"
            f"{self._build_scene_scaffold()}\n\n"
            f"{issue_focus_block}"
            f"{salvage_hint_block}"
            "## Current Script Excerpt\n"
            f"{current_script_excerpt}\n\n"
            "## Required JSON Output\n"
            "{\n"
            '  "diagnosis": {\n'
            '    "summary": "brief repair summary",\n'
            '    "applied_rule_families": ["rule_family"],\n'
            '    "remaining_risks": ["risk if any"]\n'
            "  },\n"
            '  "rewritten_script": "full screenplay text",\n'
            '  "change_summary": ["change 1", "change 2"]\n'
            "}"
        )

    def _build_compact_issue_focus_block(self) -> str:
        issues = getattr(self, "_latest_qa_issues", None)
        if not isinstance(issues, list) or not issues:
            return ""
        lines = ["## Priority Repair Focus"]
        added = 0
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            title = str(issue.get("title") or issue.get("description") or "").strip()
            if not title:
                continue
            directive = build_script_issue_rewrite_directive(issue)
            section = ""
            location = issue.get("location")
            if isinstance(location, dict):
                section = str(location.get("script_section") or "").strip()
            line = f"- {title}"
            if section:
                line += f" @ {section}"
            if directive:
                line += f": {directive}"
            lines.append(line)
            added += 1
            if added >= 5:
                break
        if added == 0:
            return ""
        lines.append("")
        return "\n".join(lines)

    def _build_forced_scaffold_prompt(self, invalid_output: str, *, include_invalid_source: bool = True) -> str:
        invalid_source_block = ""
        if include_invalid_source and str(invalid_output or "").strip():
            invalid_source_block = (
                "## Invalid Attempt Source\n"
                f"{str(invalid_output or '')[:2500]}\n\n"
            )
        return (
            f"{self._skill_block}\n\n"
            f"{self._foundation_block}\n\n"
            f"{self._execution_plan_block}\n\n"
            f"{self._repair_packet_block}\n\n"
            "## Forced Scaffold Rewrite Task\n"
            "Previous rewrite attempts failed because they returned analysis, fragments, or invalid structure.\n"
            "Write one complete episode screenplay only.\n"
            "Do not output JSON. Do not explain. Do not analyze. Do not apologize.\n"
            "Begin output immediately with the first scene header and continue writing the screenplay without any prefatory sentence.\n"
            "Write exactly the planned scene blocks using the scaffold below.\n"
            "Each scene must contain one `画面：` block, at least two `角色名：台词` lines, and one `特写：` block.\n"
            "Do not stop at a flashback label, title card, or hook label. If you open a flashback, write the flashback content fully and then return to the present scene.\n"
            "Never leave the last scene truncated. Finish the last scene with a concrete image hook.\n"
            "Resolve every issue_rewrite_directive from the repair packet.\n"
            "Keep repairs minimal and consistent. Do not invent new forensic materials, hidden methods, or chronology branches unless they are visibly staged.\n"
            "The first line must be the first scaffold scene header exactly.\n\n"
            "## Exact Scene Scaffold\n"
            f"{self._build_scene_scaffold()}\n\n"
            f"{invalid_source_block}"
            "## Current Episode Script\n"
            f"{self._current_script_content[:3200]}"
        )

    def _parse_rewrite_payload(self, raw: str) -> dict:
        return parse_json_object(
            raw,
            label="rewrite payload",
            required_keys={"diagnosis", "rewritten_script", "change_summary"},
        )

    def _normalize_scene_headers(self, text: str) -> str:
        normalized = str(text or "")
        normalized = re.sub(r"(?m)^#{3,6}(\s*场景)", r"##\1", normalized)
        normalized = re.sub(r"(?m)^#{3,6}(\s*Scene\s*[0-9]+)", r"##\1", normalized)
        normalized = re.sub(r"(?m)^场景([一二三四五六七八九十0-9]+)", r"## 场景\1", normalized)
        return normalized

    def _heading_body(self, line: str) -> str:
        normalized = str(line or "").strip()
        normalized = re.sub(r"^(?:#{1,6}|\*\*)\s*", "", normalized)
        normalized = normalized.strip("* ").strip()
        return normalized

    def _is_auxiliary_heading(self, line: str) -> bool:
        title = self._heading_body(line)
        if not title:
            return False
        title = re.sub(r"^[\[【(（].*?[\]】)）]\s*", "", title)
        if any(marker in title for marker in self.AUXILIARY_SECTION_TITLES):
            return True
        return any(
            marker in title
            for marker in (
                "道具台账",
                "资产表",
                "证据链",
                "合规自查",
                "情绪点标注",
                "疑点/反转点标注",
                "分镜细化",
                "信息钩子",
            )
        )

    def _count_scene_headers(self, text: str) -> int:
        normalized = self._normalize_scene_headers(text)
        return len(
            re.findall(
                r"(^#{2,6}\s*场景[一二三四五六七八九十0-9]+)|(^\*\*Scene\s*[0-9]+)|(^\*\*场景[一二三四五六七八九十0-9]+)",
                normalized,
                flags=re.MULTILINE,
            )
        )

    def _count_dialogue_lines(self, text: str) -> int:
        return len(re.findall(r"^[^\n：]{1,20}：.+$", text, flags=re.MULTILINE))

    def _contains_enough_visual_support(self, text: str, scene_count: int) -> bool:
        markers = ["画面：", "特写：", "镜头：", "动作：", "近景：", "远景："]
        total = sum(text.count(marker) for marker in markers)
        return total >= scene_count

    def _scene_blocks_have_enough_content(self, text: str) -> bool:
        normalized = self._normalize_scene_headers(text)
        matches = list(re.finditer(r"(?m)^#{2,6}\s*场景[一二三四五六七八九十0-9]+.*$", normalized))
        if not matches:
            return False
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            block = normalized[start:end].strip()
            if len(block) < 80:
                return False
            if "画面：" not in block and "特写：" not in block:
                return False
            if self._count_dialogue_lines(block) < 1:
                return False
        return True

    def _validate_rewritten_script_text(self, rewritten_script: str, *, strict_screenplay: bool = False) -> None:
        rewritten_script = self._normalize_scene_headers(rewritten_script)
        if not rewritten_script:
            raise ValueError("Rewrite result missing rewritten_script.")

        has_scene_structure = bool(
            re.search(
                r"(^#{2,6}\s*场景)|(^\*\*Scene\s*[0-9]+)|(^\*\*场景)|(^Scene\s*[0-9]+)",
                rewritten_script,
                flags=re.MULTILINE,
            )
        )
        if len(rewritten_script) < 60 and not has_scene_structure:
            raise ValueError("Rewrite result rewritten_script is too short to be credible.")
        if len(rewritten_script) < (400 if strict_screenplay else 180):
            raise ValueError("Rewrite result rewritten_script is too short to be a complete episode draft.")

        for fragment in self.META_FRAGMENTS:
            if fragment in rewritten_script:
                raise ValueError(f"Rewrite result still contains planning/meta fragment: {fragment}")

        scene_count = self._count_scene_headers(rewritten_script)
        expected_scene_count = max(2, len(getattr(self, "_expected_scene_names", []) or []))
        if scene_count < expected_scene_count:
            raise ValueError("Rewrite result is missing required scene headers.")

        if strict_screenplay:
            if not self._scene_blocks_have_enough_content(rewritten_script):
                raise ValueError("Rewrite result has incomplete or placeholder-like scene blocks.")
            dialogue_count = self._count_dialogue_lines(rewritten_script)
            if dialogue_count < max(4, scene_count * 2):
                raise ValueError("Rewrite result does not contain enough playable dialogue.")

            if not self._contains_enough_visual_support(rewritten_script, scene_count):
                raise ValueError("Rewrite result does not contain enough visual/action support.")

    def _extract_salvage_hints(self, raw: str) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        selected: list[str] = []
        seen: set[str] = set()
        keywords = (
            "trigger",
            "transition",
            "motive",
            "motivation",
            "clarify",
            "scene",
            "prop",
            "evidence",
            "character",
            "visible",
            "hidden",
            "杩囨浮",
            "鍔ㄦ満",
            "瑙﹀彂",
            "鏄庣‘",
            "閬撳叿",
            "璇佹嵁",
            "浜鸿",
            "鍦烘櫙",
            "鍙拌瘝",
        )
        for line in lines:
            normalized = line.lstrip("-*0123456789. )").strip()
            lower = normalized.lower()
            if len(normalized) < 12:
                continue
            if normalized.startswith(("##", "{", "}", '"')):
                continue
            if "return only valid json" in lower or "need answer json" in lower:
                continue
            if any(token in lower for token in keywords):
                if normalized not in seen:
                    selected.append(f"- {normalized}")
                    seen.add(normalized)
            if len(selected) >= 8:
                break
        return "\n".join(selected)

    def _looks_like_analysis_only_output(self, raw: str) -> bool:
        text = str(raw or "").strip()
        if not text:
            return True
        if self._count_scene_headers(text) > 0 and self._count_dialogue_lines(text) >= 2:
            return False
        opening_lines = "\n".join(text.splitlines()[:16]).lower()
        analysis_markers = (
            "the user wants me",
            "let me analyze",
            "let me think",
            "issues to repair",
            "key issues to fix",
            "the current script has",
            "the current script is incomplete",
        )
        marker_hits = sum(1 for marker in analysis_markers if marker in opening_lines)
        return marker_hits >= 2

    def _extract_object_after_key(self, text: str, key: str) -> dict | None:
        marker = f'"{key}"'
        marker_index = text.find(marker)
        if marker_index < 0:
            return None
        start = text.find("{", marker_index)
        if start < 0:
            return None
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth -= 1
                if depth == 0:
                    fragment = text[start:index + 1]
                    try:
                        return parse_json_object(fragment, label=f"rewrite {key} object")
                    except Exception:
                        return None
        return None

    def _extract_json_string_after_key(self, text: str, key: str) -> str:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*"', text)
        if not match:
            return ""
        index = match.end()
        chars: list[str] = []
        while index < len(text):
            char = text[index]
            if char == '"':
                return "".join(chars).strip()
            if char != "\\":
                chars.append(char)
                index += 1
                continue

            index += 1
            if index >= len(text):
                break
            escaped = text[index]
            if escaped == "n":
                chars.append("\n")
            elif escaped == "r":
                chars.append("\r")
            elif escaped == "t":
                chars.append("\t")
            elif escaped in {'"', "\\", "/"}:
                chars.append(escaped)
            elif escaped == "u":
                hex_digits = text[index + 1:index + 5]
                if len(hex_digits) == 4 and all(item in "0123456789abcdefABCDEF" for item in hex_digits):
                    chars.append(chr(int(hex_digits, 16)))
                    index += 4
                else:
                    break
            else:
                chars.append(escaped)
            index += 1
        return "".join(chars).strip()

    def _extract_string_list_after_key(self, text: str, key: str) -> list[str]:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*(\[[^\]]*\])', text, flags=re.DOTALL)
        if not match:
            return []
        try:
            payload = json.loads(match.group(1))
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        return [str(item).strip() for item in payload if str(item).strip()]

    def _salvage_rewrite_payload(self, raw: str) -> dict | None:
        text = strip_code_fences(raw)
        if not text:
            return None

        rewritten_script = self._normalize_scene_headers(self._extract_json_string_after_key(text, "rewritten_script"))
        if not rewritten_script:
            return None

        return {
            "diagnosis": self._extract_object_after_key(text, "diagnosis") or {},
            "rewritten_script": rewritten_script,
            "change_summary": self._extract_string_list_after_key(text, "change_summary"),
        }

    def _coerce_rewritten_script_to_screenplay(self, rewritten_script: str) -> str:
        normalized = self._normalize_scene_headers(str(rewritten_script or "").strip())
        if not normalized:
            return ""
        if normalized.startswith("## 场景") and "## 剧集设定" not in normalized and "## 集级大纲" not in normalized:
            return self._strip_screenplay_meta_lines(normalized)
        try:
            return self._strip_screenplay_meta_lines(self._extract_script_body(normalized))
        except Exception:
            return self._strip_screenplay_meta_lines(normalized)

    def _validate_rewrite_payload(self, payload: dict) -> tuple[str, dict]:
        rewritten_script = self._coerce_rewritten_script_to_screenplay(str(payload.get("rewritten_script") or "").strip())
        self._validate_rewritten_script_text(rewritten_script, strict_screenplay=True)

        diagnosis = payload.get("diagnosis")
        if not isinstance(diagnosis, dict):
            diagnosis = {}

        change_summary = payload.get("change_summary")
        if not isinstance(change_summary, list):
            change_summary = []

        normalized = {
            "diagnosis": diagnosis,
            "change_summary": [str(item).strip() for item in change_summary if str(item).strip()],
        }
        return rewritten_script, normalized

    def _best_scene_start(self, text: str, patterns: Iterable[str], progress_markers: Iterable[str]) -> int | None:
        best_start: int | None = None
        best_score = -1
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.MULTILINE):
                start = match.start()
                suffix = text[start:]
                score = sum(1 for marker in progress_markers if marker in suffix)
                if score > best_score or (score == best_score and (best_start is None or start > best_start)):
                    best_start = start
                    best_score = score
        return best_start

    def _score_screenplay_candidate(self, text: str) -> int:
        scene_count = self._count_scene_headers(text)
        dialogue_count = self._count_dialogue_lines(text)
        visual_count = sum(text.count(marker) for marker in ["画面：", "特写：", "镜头：", "动作：", "近景：", "远景："])
        meta_penalty = sum(50 for fragment in self.META_FRAGMENTS if fragment in text)
        return scene_count * 100 + dialogue_count * 10 + visual_count * 5 - meta_penalty

    def _looks_like_meta_line(self, line: str) -> bool:
        normalized = str(line or "").strip()
        if not normalized:
            return False
        if self._is_auxiliary_heading(normalized):
            return True
        if self._is_screenplay_meta_line(normalized):
            return True
        lower = normalized.lower()
        if any(fragment.lower() in lower for fragment in self.META_FRAGMENTS):
            return True
        meta_prefixes = (
            "让我",
            "让我们",
            "我需要",
            "我注意到",
            "实际上",
            "但等等",
            "等等",
            "回顾一下",
            "修复方法",
            "修复清单",
            "问题",
            "设定",
            "场景1流程",
            "场景2流程",
            "场景一流程",
            "场景二流程",
            "物理证据",
            "原始草稿",
            "现在开始",
            "下面开始",
            "继续：",
            "离开后：",
            "细节顺序：",
            "现在断绳头：",
            "然后骨架：",
            "然后门威胁：",
            "在场景2中",
            "所以最后的包裹包含",
            "好，重写",
            "然后“",
            "然后\"",
        )
        if normalized.startswith(meta_prefixes):
            return True
        if normalized.startswith("（"):
            return True
        if normalized.startswith("- "):
            return True
        if re.match(r"^\d+\.\s*\*\*.+\*\*", normalized):
            return True
        if re.match(r"^-\s+\*\*.+\*\*", normalized):
            return True
        return False

    def _is_screenplay_meta_line(self, line: str) -> bool:
        normalized = str(line or "").strip()
        if not normalized.startswith("**"):
            return False
        match = re.match(r"^\*\*(.+?)\*\*[：:]", normalized)
        if not match:
            return False
        return match.group(1).strip() in self.SCREENPLAY_META_LABELS

    def _is_screenplay_annotation_line(self, line: str) -> bool:
        normalized = str(line or "").strip()
        match = re.match(r"^【([^：】]+)[：:].*】?$", normalized)
        if not match:
            return False
        return match.group(1).strip() in self.SCREENPLAY_ANNOTATION_LABELS

    def _strip_screenplay_meta_lines(self, text: str) -> str:
        cleaned: list[str] = []
        for raw_line in str(text or "").splitlines():
            normalized = raw_line.strip()
            if self._is_auxiliary_heading(normalized):
                continue
            if self._is_screenplay_meta_line(normalized):
                continue
            if self._is_screenplay_annotation_line(normalized):
                continue
            if normalized == "---":
                continue
            if not normalized:
                if cleaned and cleaned[-1] != "":
                    cleaned.append("")
                continue
            cleaned.append(raw_line.rstrip())
        while cleaned and cleaned[-1] == "":
            cleaned.pop()
        return "\n".join(cleaned).strip()

    def _sanitize_scene_block(self, block: str) -> str:
        lines = [line.rstrip() for line in str(block or "").splitlines()]
        if not lines:
            return ""
        cleaned: list[str] = []
        screenplay_started = False
        for index, line in enumerate(lines):
            normalized = line.strip()
            if index == 0:
                cleaned.append(normalized)
                continue
            if not normalized:
                if cleaned and cleaned[-1] != "":
                    cleaned.append("")
                continue
            if normalized.startswith("```"):
                continue
            if re.match(r"^#{1,6}\s+", normalized) and self._is_auxiliary_heading(normalized):
                break
            if screenplay_started and re.match(r"^#{1,6}\s*(?!场景|Scene\s*\d+)", normalized):
                break
            if self._looks_like_meta_line(normalized):
                if screenplay_started:
                    break
                continue
            if "：" in normalized or any(
                normalized.startswith(marker)
                for marker in ("画面：", "特写：", "镜头：", "动作：", "近景：", "远景：")
            ):
                screenplay_started = True
            cleaned.append(line.rstrip())
        return "\n".join(cleaned).strip()

    def _split_inline_dialogue_line(self, line: str) -> list[str]:
        normalized = str(line or "").strip()
        if not normalized or re.match(r"^(?:和尚)?[\u4e00-\u9fffA-Za-z0-9]{1,12}：", normalized):
            return [normalized] if normalized else []
        if any(
            normalized.startswith(marker)
            for marker in ("画面：", "特写：", "镜头：", "动作：", "近景：", "远景：", "音效：", "旁白：", "【")
        ):
            return [normalized]

        match = re.match(
            r"^(?P<prefix>(?:和尚)?[甲乙丙丁戊己庚辛壬癸][^“”\"]*?)(?P<quote>[“\"])(?P<speech>.+?)[”\"]\s*$",
            normalized,
        )
        if not match:
            return [normalized]

        prefix = match.group("prefix").strip(" ，,。；;：:")
        speech = match.group("speech").strip()
        speaker_match = re.match(
            r"^(?P<speaker>(?:和尚)?[甲乙丙丁戊己庚辛壬癸])(?P<action>.*)$",
            prefix,
        )
        if not speaker_match or not speech:
            return [normalized]

        speaker = speaker_match.group("speaker").strip()
        action = speaker_match.group("action").strip(" ，,。；;：:")
        rebuilt: list[str] = []
        if action:
            rebuilt.append(f"{speaker}{action}。")
        rebuilt.append(f"{speaker}：{speech}")
        return rebuilt

    def _normalize_dialogue_format(self, text: str) -> str:
        normalized_lines: list[str] = []
        for raw_line in str(text or "").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                if normalized_lines and normalized_lines[-1] != "":
                    normalized_lines.append("")
                continue
            normalized_lines.extend(self._split_inline_dialogue_line(stripped))

        while normalized_lines and not normalized_lines[-1]:
            normalized_lines.pop()
        return "\n".join(normalized_lines).strip()

    def _looks_like_actual_scene_header(self, header: str) -> bool:
        normalized = str(header or "").strip()
        if not normalized:
            return False
        if self._is_auxiliary_heading(normalized):
            return False
        if any(token in normalized for token in ["流程", "结构", "细节", "必须发生", "修好", "起草"]):
            return False
        if re.search(r"\[[^\]]+\]|【[^】]+】", normalized):
            return True
        if re.match(r"^#{2,6}\s*场景[一二三四五六七八九十0-9]+\s*[·\-.：: ]+\S+", normalized):
            return True
        return bool(re.match(r"^#{2,6}\s*Scene\s*[0-9]+\s*[:：]\s*[A-Za-z0-9][^\n]*$", normalized))

    def _extract_best_plaintext_scene_script(self, text: str) -> str | None:
        normalized = self._normalize_scene_headers(text)
        header_pattern = r"(?m)^#{2,6}\s*(场景[一二三四五六七八九十0-9]+.*|Scene\s*[0-9]+.*)$"
        matches = list(re.finditer(header_pattern, normalized))
        if not matches:
            return None

        best_by_scene: dict[str, tuple[int, int, str]] = {}
        order_by_scene: dict[str, int] = {}
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            raw_block = normalized[start:end].strip()
            block = self._sanitize_scene_block(raw_block)
            if not block:
                continue
            header = block.splitlines()[0].strip()
            if not self._looks_like_actual_scene_header(header):
                continue
            scene_key_match = re.match(r"^#{2,6}\s*(场景[一二三四五六七八九十0-9]+|Scene\s*[0-9]+)", header)
            scene_key = scene_key_match.group(1) if scene_key_match else header
            score = self._score_screenplay_candidate(block)
            if scene_key not in order_by_scene:
                order_by_scene[scene_key] = len(order_by_scene)
            previous = best_by_scene.get(scene_key)
            if previous is None or score >= previous[0]:
                best_by_scene[scene_key] = (score, order_by_scene[scene_key], block)

        if not best_by_scene:
            return None

        ordered_blocks = [
            item[2]
            for item in sorted(best_by_scene.values(), key=lambda row: row[1])
            if item[2].strip()
        ]
        candidate = "\n\n".join(ordered_blocks).strip()
        if not candidate:
            return None
        return candidate

    def _extract_best_fenced_block(self, text: str) -> str | None:
        blocks = re.findall(r"```(?:[^\n`]*)\n(.*?)```", text, flags=re.DOTALL)
        if not blocks:
            return None
        ranked = sorted(
            ((self._score_screenplay_candidate(block), block.strip()) for block in blocks if block.strip()),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] <= 0:
            return None
        return ranked[0][1]

    def _looks_like_placeholder_block(self, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return True
        return "..." in normalized or "…" in normalized

    def _looks_like_scene_opening_without_header(self, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return False
        if normalized.startswith("## 场景"):
            return False
        opening_markers = ("画面：", "特写：", "镜头：", "动作：")
        return any(normalized.startswith(marker) for marker in opening_markers)

    def _synthesized_scene_header(self, scene_index: int) -> str:
        numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        numeral = numerals[scene_index - 1] if 1 <= scene_index <= len(numerals) else str(scene_index)
        expected_names = getattr(self, "_expected_scene_names", []) or []
        name = ""
        if scene_index - 1 < len(expected_names):
            name = str(expected_names[scene_index - 1]).strip()
        if name:
            return f"## 场景{numeral} [{name}]"
        return f"## 场景{numeral}"
    def _is_redundant_fragment(self, block: str, assembled: list[str]) -> bool:
        normalized = str(block or "").strip()
        if not normalized:
            return True
        for existing in assembled:
            candidate = str(existing or "").strip()
            if not candidate:
                continue
            if normalized == candidate:
                return True
            if len(normalized) <= len(candidate) and normalized in candidate:
                return True
            if len(candidate) < len(normalized) and candidate in normalized and len(candidate) >= 60:
                return True
        return False

    def _extract_compound_fenced_script(self, text: str) -> str | None:
        blocks = [
            block.strip()
            for block in re.findall(r"```(?:[^\n`]*)\n(.*?)```", text, flags=re.DOTALL)
            if block.strip()
        ]
        if not blocks:
            return None

        assembled: list[str] = []
        seen_blocks: set[str] = set()
        current_scene_index = 0
        expected_scene_count = max(2, len(getattr(self, "_expected_scene_names", []) or []))

        for block in blocks:
            if self._looks_like_placeholder_block(block):
                continue
            normalized = block.strip()
            if normalized in seen_blocks or self._is_redundant_fragment(normalized, assembled):
                continue

            has_header = bool(re.match(r"^##\s*场景", normalized))
            if has_header:
                current_scene_index += 1
                assembled.append(normalized)
                seen_blocks.add(normalized)
                continue

            if not assembled:
                continue

            if (
                current_scene_index < expected_scene_count
                and self._looks_like_scene_opening_without_header(normalized)
                and any(self._is_screenplay_annotation_line(part) for part in assembled[-2:])
            ):
                current_scene_index += 1
                assembled.append(self._synthesized_scene_header(current_scene_index))

            if normalized not in seen_blocks:
                assembled.append(normalized)
                seen_blocks.add(normalized)

        candidate = "\n\n".join(part for part in assembled if part.strip()).strip()
        if not candidate:
            return None
        return candidate

    def _extract_script_body(self, raw: str) -> str:
        text = self._normalize_scene_headers(strip_code_fences(raw))
        if not text:
            raise ValueError("Fallback rewrite returned empty output.")

        fenced_candidate = self._extract_best_fenced_block(str(raw or ""))
        if fenced_candidate:
            try:
                normalized_fenced_candidate = self._normalize_dialogue_format(fenced_candidate)
                self._validate_rewritten_script_text(normalized_fenced_candidate, strict_screenplay=True)
                return normalized_fenced_candidate
            except Exception:
                pass

        compound_fenced_candidate = self._extract_compound_fenced_script(str(raw or ""))
        if compound_fenced_candidate:
            normalized_compound_fenced_candidate = self._normalize_dialogue_format(compound_fenced_candidate)
            self._validate_rewritten_script_text(normalized_compound_fenced_candidate, strict_screenplay=True)
            return normalized_compound_fenced_candidate

        plaintext_scene_candidate = self._extract_best_plaintext_scene_script(text)
        if plaintext_scene_candidate:
            normalized_plaintext_scene_candidate = self._normalize_dialogue_format(plaintext_scene_candidate)
            self._validate_rewritten_script_text(normalized_plaintext_scene_candidate, strict_screenplay=True)
            return normalized_plaintext_scene_candidate

        patterns = [
            r"^#{2,6}\s*场景一",
            r"^#{2,6}\s*场景1",
            r"^场景一",
            r"^场景1",
            r"^\*\*Scene 1",
            r"^\*\*场景一",
            r"^Scene 1[:：]",
        ]
        progress_markers = [
            "场景二",
            "场景三",
            "Scene 2",
            "Scene 3",
            "## 场景二",
            "## 场景三",
        ]
        best_start = self._best_scene_start(text, patterns, progress_markers)
        if best_start is not None:
            text = text[best_start:].strip()

        cut_positions = [text.find(fragment) for fragment in self.META_FRAGMENTS if text.find(fragment) > 0]
        if cut_positions:
            text = text[:min(cut_positions)].strip()

        text = self._normalize_dialogue_format(text)
        self._validate_rewritten_script_text(text, strict_screenplay=True)
        return text

    def _call_structured_rewrite(self, prompt: str, system: str) -> tuple[str, dict]:
        previous_output = ""
        previous_error = ""
        last_error: Exception | None = None
        salvage_hints: list[str] = []
        for attempt in range(2):
            raw = call_llm(
                prompt if attempt == 0 else self._build_rewrite_prompt(
                    self._current_script_content,
                    self._skill_block,
                    self._foundation_block,
                    self._generation_brief_block,
                    self._execution_plan_block,
                    self._repair_packet_block,
                    previous_invalid_output=previous_output,
                    previous_error=previous_error,
                ),
                system=system,
                estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
                temperature=0.1,
            )
            try:
                payload = self._parse_rewrite_payload(raw)
                return self._validate_rewrite_payload(payload)
            except Exception as exc:
                salvaged = self._salvage_rewrite_payload(raw)
                if salvaged:
                    try:
                        return self._validate_rewrite_payload(salvaged)
                    except Exception:
                        pass
                previous_output = str(raw or "")
                previous_error = str(exc)
                salvage_hint = self._extract_salvage_hints(previous_output)
                if salvage_hint:
                    salvage_hints.append(salvage_hint)
                write_debug_output(self._debug_output_path(attempt + 1), previous_output)
                last_error = exc
                logger.warning("Rewrite output invalid on attempt %s: %s", attempt + 1, exc)
                if self._looks_like_analysis_only_output(previous_output):
                    break
        self._fallback_salvage_hints = "\n".join(
            hint for hint in salvage_hints if hint.strip()
        ).strip()
        compact_prompt = self._build_compact_json_fallback_prompt()
        for compact_attempt in range(2):
            raw = call_llm(
                compact_prompt,
                system=system,
                estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT,
                temperature=0.0,
            )
            write_debug_output(self._compact_json_debug_output_path(compact_attempt + 1), str(raw or ""))
            try:
                payload = self._parse_rewrite_payload(raw)
                return self._validate_rewrite_payload(payload)
            except Exception as exc:
                salvaged = self._salvage_rewrite_payload(raw)
                if salvaged:
                    try:
                        return self._validate_rewrite_payload(salvaged)
                    except Exception:
                        pass
                last_error = exc
        raise last_error or ValueError("Rewrite output invalid after retries.")

    def _run_script_only_fallback(self, system: str) -> tuple[str, dict]:
        raw = call_llm(
            self._build_script_only_fallback_prompt(),
            system=system,
            estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
            temperature=0.1,
        )
        write_debug_output(self._fallback_debug_output_path(), raw)
        try:
            rewritten_script = self._extract_script_body(raw)
        except Exception:
            if self._looks_like_analysis_only_output(raw):
                rebuilt_raw = call_llm(
                    self._build_compiler_rebuild_prompt(),
                    system=system,
                    estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
                    temperature=0.0,
                )
                write_debug_output(self._fallback_forced_debug_output_path(), rebuilt_raw)
                try:
                    rewritten_script = self._extract_script_body(rebuilt_raw)
                except Exception:
                    forced_raw = call_llm(
                        self._build_forced_scaffold_prompt(str(raw or ""), include_invalid_source=False),
                        system=system,
                        estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
                        temperature=0.0,
                    )
                    write_debug_output(self._fallback_forced_debug_output_path(), forced_raw)
                    rewritten_script = self._extract_script_body(forced_raw)
            else:
                normalized_raw = call_llm(
                    self._build_script_normalization_prompt(str(raw or "")),
                    system=system,
                    estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
                    temperature=0.0,
                )
                write_debug_output(self._fallback_normalized_debug_output_path(), normalized_raw)
                try:
                    rewritten_script = self._extract_script_body(normalized_raw)
                except Exception:
                    rebuilt_raw = call_llm(
                        self._build_compiler_rebuild_prompt(),
                        system=system,
                        estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
                        temperature=0.0,
                    )
                    write_debug_output(self._fallback_forced_debug_output_path(), rebuilt_raw)
                    try:
                        rewritten_script = self._extract_script_body(rebuilt_raw)
                    except Exception:
                        forced_raw = call_llm(
                            self._build_forced_scaffold_prompt(str(normalized_raw or raw or "")),
                            system=system,
                            estimated_tokens=config.ESTIMATED_TOKENS_LARGE,
                            temperature=0.0,
                        )
                        write_debug_output(self._fallback_forced_debug_output_path(), forced_raw)
                        rewritten_script = self._extract_script_body(forced_raw)
        report = {
            "diagnosis": {
                "summary": "Fallback rewrite completed in screenplay mode after structured output contract failures.",
                "applied_rule_families": [],
                "remaining_risks": ["Structured diagnosis was synthesized by fallback handling."],
            },
            "change_summary": ["Recovered a full rewritten episode through screenplay fallback mode."],
        }
        return rewritten_script, report

    def _debug_output_path(self, attempt: int):
        return config.output_path(
            self._book_title,
            "scripts",
            f"episode_{self._episode:02d}_rewrite_invalid_attempt_{attempt}.txt",
        )

    def _fallback_debug_output_path(self):
        return config.output_path(
            self._book_title,
            "scripts",
            f"episode_{self._episode:02d}_rewrite_fallback_raw.txt",
        )

    def _fallback_normalized_debug_output_path(self):
        return config.output_path(
            self._book_title,
            "scripts",
            f"episode_{self._episode:02d}_rewrite_fallback_normalized.txt",
        )

    def _compact_json_debug_output_path(self, attempt: int):
        return config.output_path(
            self._book_title,
            "scripts",
            f"episode_{self._episode:02d}_rewrite_compact_json_attempt_{attempt}.txt",
        )

    def _fallback_forced_debug_output_path(self):
        return config.output_path(
            self._book_title,
            "scripts",
            f"episode_{self._episode:02d}_rewrite_fallback_forced.txt",
        )

    def run(self, episode: int) -> str:
        try:
            with self.session() as session:
                book = session.get(Book, self.book_id)
                if not book:
                    raise ValueError(f"Book {self.book_id} not found")
                self._book_title = book.title
                self._episode = episode

                script = session.query(Script).filter(
                    Script.book_id == self.book_id,
                    Script.episode == episode,
                ).first()
                if not script:
                    raise ValueError(f"Script for episode {episode} not found.")

                latest_qa_issues = load_latest_script_qa_issues(self.book_id, episode)
                self._latest_qa_issues = latest_qa_issues
                self._episode_outline = self._load_episode_outline(session, episode)
                self._current_script_content = script.content or ""
                self._expected_scene_names = self._load_expected_scene_names()

                self._skill_block = build_production_skill_prompt_block(self.book_id, "script")
                self._foundation_block = build_script_skill_foundation_prompt_block(
                    self.book_id,
                    episode_outline=self._episode_outline,
                    qa_issues=latest_qa_issues,
                    script_content=script.content,
                )
                self._generation_brief_block = build_script_generation_brief_prompt_block(
                    self.book_id,
                    episode_outline=self._episode_outline,
                    qa_issues=latest_qa_issues,
                    script_content=script.content,
                )
                self._execution_plan_block = build_script_skill_execution_plan_prompt_block(
                    self.book_id,
                    episode_outline=self._episode_outline,
                    qa_issues=latest_qa_issues,
                )
                self._repair_packet_block = build_script_skill_repair_packet_prompt_block(
                    self.book_id,
                    episode_outline=self._episode_outline,
                    qa_issues=latest_qa_issues,
                    script_content=script.content,
                )
                
                # Store structural validation prompt for use in _build_rewrite_prompt
                repair_packet = build_script_skill_repair_packet(
                    self.book_id,
                    episode_outline=self._episode_outline,
                    qa_issues=latest_qa_issues,
                    script_content=script.content,
                )
                self._structural_validation_prompt = repair_packet.get("structural_validation_prompt", "")

                prompt = self._build_rewrite_prompt(
                    self._current_script_content,
                    self._skill_block,
                    self._foundation_block,
                    self._generation_brief_block,
                    self._execution_plan_block,
                    self._repair_packet_block,
                )
                system = (
                    "You are a short-drama screenplay repair agent. You must follow the active Production Skill, repair priorities, and output contract."
                    "On the structured path, return valid JSON only. Do not output chain-of-thought, drafts, checklists, or extra explanation."
                )
                try:
                    rewritten_script, rewrite_report = self._call_structured_rewrite(prompt, system)
                except Exception as exc:
                    logger.warning("Structured rewrite failed, entering screenplay fallback: %s", exc)
                    rewritten_script, rewrite_report = self._run_script_only_fallback(
                        "You are a short-drama screenplay repair agent. Return only the final screenplay text. Do not output chain-of-thought, drafts, or explanation."
                    )

                output = config.output_path(book.title, "scripts", f"episode_{episode:02d}_script_v2.md")
                report_output = config.output_path(book.title, "scripts", f"episode_{episode:02d}_rewrite_report.json")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rewritten_script, encoding="utf-8")
                report_output.write_text(json.dumps(rewrite_report, ensure_ascii=False, indent=2), encoding="utf-8")

                script.content = rewritten_script
                script.word_count = len(rewritten_script)
                session.commit()

            return str(output)
        except Exception as exc:
            logger.error("Rewrite failed for book %s ep %s: %s", self.book_id, episode, exc)
            raise
