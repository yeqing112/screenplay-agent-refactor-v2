import json
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from agents.rewrite import RewriteAgent
from models import Book, EpisodeOutline, KV, QAResult, Script, Session, init_db


class RewriteAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991303
        self.episode = 1
        self.kv_key = f"product_workspace:production_skill:{self.book_id}"
        self.book_title = "Rewrite Agent Demo"
        self.script_text = "\n".join(
            [
                "**Scene 1:[well-morning]**",
                "The new monk is splashed awake.",
                "**Scene 2:[hall-night]**",
                "The monk reveals a hidden token.",
            ]
        )
        with Session() as session:
            session.query(KV).filter(KV.key == self.kv_key).delete()
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(EpisodeOutline).filter(EpisodeOutline.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title=self.book_title,
                    filename="rewrite-agent-demo.txt",
                    chapter_count=1,
                    total_words=len(self.script_text),
                    status="draft",
                )
            )
            session.add(
                EpisodeOutline(
                    book_id=self.book_id,
                    episode=self.episode,
                    title="Episode 1",
                    core_event="The monk returns to investigate the temple.",
                    opening_hook="A bucket of cold water wakes him up.",
                    core_conflict="His hidden identity conflicts with the token reveal.",
                    climax="The abbot token is exposed.",
                    ending_hook="The next-episode conflict escalates.",
                    characters="Monk A, Monk B",
                    scenes="well-morning, hall-night",
                )
            )
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=self.episode,
                    content=self.script_text,
                    word_count=len(self.script_text),
                    status="draft",
                )
            )
            session.add(
                QAResult(
                    book_id=self.book_id,
                    episode=self.episode,
                    result=json.dumps(
                        {
                            "issues": [
                                {
                                    "type": "continuity",
                                    "severity": "high",
                                    "title": "token chain unclear",
                                    "description": "The token lacks any setup before the reveal.",
                                    "location": {"script_section": "Scene 2"},
                                }
                            ],
                            "overall_score": 6,
                        },
                        ensure_ascii=False,
                    ),
                    error_count=1,
                )
            )
            session.commit()

    def tearDown(self):
        output_path = config.output_path(self.book_title, "scripts", f"episode_{self.episode:02d}_script_v2.md")
        best_path = config.output_path(self.book_title, "scripts", f"episode_{self.episode:02d}_script_best.md")
        report_path = config.output_path(self.book_title, "scripts", f"episode_{self.episode:02d}_rewrite_report.json")
        for path in [output_path, best_path, report_path]:
            try:
                file_path = Path(path)
                if file_path.exists():
                    file_path.unlink()
            except OSError:
                pass

        with Session() as session:
            session.query(KV).filter(KV.key == self.kv_key).delete()
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(EpisodeOutline).filter(EpisodeOutline.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_rewrite_agent_persists_only_rewritten_script_and_sidecar_report(self):
        captured = {}

        def fake_call(prompt, system=None, **kwargs):
            captured["prompt"] = prompt
            captured["system"] = system
            return json.dumps(
                {
                    "diagnosis": {
                        "summary": "fixed continuity",
                        "applied_rule_families": ["prop_evidence_continuity"],
                        "remaining_risks": ["ending hook still moderate"],
                    },
                    "rewritten_script": "\n".join(
                        [
                            "## 场景一 [well-morning]",
                            "画面：" + ("The monk wakes in a shock and instinctively checks the hidden token. " * 10),
                            "Monk B：Keep your head down.",
                            "Monk A：I only need one more look.",
                            "特写：" + ("The token cord catches on his sleeve seam. " * 8),
                            "## 场景二 [hall-night]",
                            "画面：" + ("Under cover of night, the monk returns to the hall and corners the others. " * 10),
                            "Monk B：You should have stayed silent.",
                            "Monk A：You buried the sutra secret with the token.",
                            "特写：" + ("The token surface reflects the lamp before the reveal lands. " * 8),
                        ]
                    ),
                    "change_summary": ["Added token setup", "Compressed ending dialogue"],
                },
                ensure_ascii=False,
            )

        with patch("agents.rewrite.call_llm", side_effect=fake_call):
            output = RewriteAgent(self.book_id).run(self.episode)

        self.assertIn("## Script Skill Repair Packet", captured["prompt"])
        self.assertIn("Treat `Script Generation Brief` as the primary structural map", captured["prompt"])
        self.assertIn("Treat `story_fact_sheet` as the fact-locked source of truth", captured["prompt"])
        self.assertIn("Treat each `scene_compilation_card` as a required scene-by-scene construction card", captured["prompt"])
        self.assertIn("Treat each `scene_execution_card` as the execution-level contract", captured["prompt"])
        self.assertIn("Treat `prop_timeline_brief` as the scene-by-scene ledger", captured["prompt"])
        self.assertIn("Treat `structure_focus` and `stage_repair_priorities` as the repair-order contract", captured["prompt"])
        self.assertIn("Treat `stage_repair_agenda` as the ordered repair worklist", captured["prompt"])
        self.assertIn("Treat `scene_repair_agenda` as the per-scene repair contract", captured["prompt"])
        self.assertIn("Preserve the existing scene count and scene order", captured["prompt"])
        self.assertIn("driver, visual anchor, new evidence goal, clue reuse goal, and exit delta", captured["prompt"])
        self.assertIn("rewritten_script", captured["prompt"])
        self.assertIn("Production Skill", captured["prompt"])
        self.assertIn("Resolve every issue_rewrite_directive", captured["prompt"])
        self.assertIn("visible transition or acquisition beat", captured["prompt"])
        self.assertIn("bound portraits, character sheets, or asset canon", captured["prompt"])
        self.assertIn("habitual phrase, draggy cadence, excuse pattern, or ritual opener", captured["prompt"])
        self.assertIn("bound public persona is lazy, perfunctory, timid, evasive, or soft", captured["prompt"])
        self.assertIn("quietly notices, delays, withholds, or pointedly skips", captured["prompt"])
        self.assertIn("lazy, evasive, timid, or perfunctory character must search, detain, escort, or enforce rules", captured["prompt"])
        self.assertIn("announce a custody destination such as a storehouse, shed, cell, or back room", captured["prompt"])
        self.assertIn("Keep relative time phrases consistent", captured["prompt"])
        self.assertIn("body-action logic physically playable", captured["prompt"])
        self.assertIn("high-value props on one coherent timeline", captured["prompt"])
        self.assertIn("smallest consistent adjustment", captured["prompt"])
        self.assertIn("hidden method, ritual, code, or evidence-reveal technique", captured["prompt"])
        self.assertIn("later reveal depends on a hidden inscription, carved stroke, sealed label, or covered mark", captured["prompt"])
        self.assertIn("plot-relevant sound cue", captured["prompt"])
        self.assertIn("visible surface evidence separate from hidden underlayer inference", captured["prompt"])
        self.assertIn("When dialogue names a decisive clue, theft, missing item, or fresh damage for the first time", captured["prompt"])
        self.assertIn("Once a prop has been pocketed, wrapped, hidden, or moved", captured["prompt"])
        self.assertIn("If a prop was discarded, dropped into water, kicked aside, or confiscated earlier", captured["prompt"])
        self.assertIn("do not show the same character immediately discovering or re-taking it again", captured["prompt"])
        self.assertIn("second check must be justified by a new trigger", captured["prompt"])
        self.assertIn("If a location is searched earlier but yields a later discovery", captured["prompt"])
        self.assertIn("If a character witnesses blood, a body trace, or a major crime clue but stays silent", captured["prompt"])
        self.assertIn("copy, torn page, extracted fragment, duplicate bundle", captured["prompt"])
        self.assertIn("Keep page numbers, counts, labels, and small evidence details stable", captured["prompt"])
        self.assertIn("Dialogue cannot claim stronger certainty than the shown evidence supports", captured["prompt"])
        self.assertIn("Shared material alone is not enough for a decisive clue match", captured["prompt"])
        self.assertIn("suspense image or shadow motif repeats", captured["prompt"])
        self.assertIn("Do not redefine the nature of the same clue later", captured["prompt"])
        self.assertIn("hidden helper tool, wax cloth, copper wire, note, or stash", captured["prompt"])
        self.assertIn("tiny physical clue such as a scratch, wax nick, pressure dent, missing corner, or thread color", captured["prompt"])
        self.assertIn("clue stays concealed under wax, cloth, mud, paper, or another cover", captured["prompt"])
        self.assertIn("clue surface or seam was already shown earlier", captured["prompt"])
        self.assertIn("searcher notices an abnormal detail but does not pursue it", captured["prompt"])
        self.assertIn("visible accusation trigger in frame", captured["prompt"])
        self.assertIn("having checked, solved, cleared, or released someone must match the actual action state", captured["prompt"])
        self.assertIn("Keep weather, light source, and visibility coherent", captured["prompt"])
        self.assertIn("reuses a prop to fake an earlier visible state", captured["prompt"])
        self.assertIn("striking clue image appears, either reuse it later in suspicion or payoff logic, or cut it", captured["prompt"])
        self.assertIn("Replace abstract inner narration such as remembering, deciding, suspecting, or filing something away", captured["prompt"])
        self.assertIn("conflict depends on an off-screen theft, missing item, injury, or alarm event", captured["prompt"])
        self.assertIn("flashback interrupts active danger", captured["prompt"])
        self.assertIn("flashback lands inside active danger, compress it into short inserts or move it to the first safe beat", captured["prompt"])
        self.assertIn("ending hook must add a fresh delta beyond what the audience already knew", captured["prompt"])
        self.assertIn("repeatedly risks exposure to move, plant, retrieve, or re-stage the same clue", captured["prompt"])
        self.assertIn("Escape or lock-breaking beats must match the shown hardware geometry", captured["prompt"])
        self.assertIn("watcher should stay ambiguous", captured["prompt"])
        self.assertIn("ending hook should still read without the final line", captured["prompt"])
        self.assertIn("return valid JSON only", captured["system"])

        output_path = Path(output)
        report_path = Path(config.output_path(self.book_title, "scripts", f"episode_{self.episode:02d}_rewrite_report.json"))
        self.assertTrue(output_path.exists())
        self.assertTrue(report_path.exists())

        rewritten = output_path.read_text(encoding="utf-8")
        self.assertIn("corners the others", rewritten)
        self.assertNotIn("change_summary", rewritten)

        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report_payload["diagnosis"]["summary"], "fixed continuity")
        self.assertEqual(report_payload["change_summary"][0], "Added token setup")

        with Session() as session:
            script = session.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == self.episode,
            ).first()

        self.assertIn("corners the others", script.content)
        self.assertNotIn("change_summary", script.content)

    def test_run_perfect_restores_best_snapshot_when_qa_regresses(self):
        qa_scores = [
            {"overall_score": 6, "issues": [{"severity": "high", "title": "needs repair"}]},
            {"overall_score": 4, "issues": [{"severity": "high", "title": "regressed"}]},
        ]

        class FakeQAAgent:
            def __init__(self, book_id):
                self.book_id = book_id

            def run(self, episode):
                return qa_scores.pop(0)

        def fake_run(agent, episode):
            with Session() as session:
                script = session.query(Script).filter(
                    Script.book_id == self.book_id,
                    Script.episode == episode,
                ).first()
                script.content = "REGRESSED SCRIPT"
                script.word_count = len(script.content)
                session.commit()
            output = config.output_path(self.book_title, "scripts", f"episode_{episode:02d}_script_v2.md")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("REGRESSED SCRIPT", encoding="utf-8")
            return str(output)

        with patch("agents.qa.QAAgent", FakeQAAgent), patch.object(RewriteAgent, "run", fake_run):
            result_path = RewriteAgent(self.book_id).run_perfect(self.episode, target_score=9, max_rounds=1)

        self.assertTrue(result_path.endswith("episode_01_script_best.md"))
        self.assertEqual(Path(result_path).read_text(encoding="utf-8"), self.script_text)
        with Session() as session:
            script = session.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == self.episode,
            ).first()
        self.assertEqual(script.content, self.script_text)

    def test_dialogue_refinement_rejects_truncated_long_script_output(self):
        long_script = "\n".join(
            [
                "## 场景一 [well-morning]",
                "画面：" + ("井边水声和法牌线索持续推进。" * 260),
                "## 场景二 [hall-night]",
                "画面：" + ("夜厅烛火和账册证据持续推进。" * 260),
            ]
        )
        with Session() as session:
            script = session.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == self.episode,
            ).first()
            script.content = long_script
            script.word_count = len(long_script)
            session.commit()

        captured = {}

        def fake_call(prompt, system=None, **kwargs):
            captured["prompt"] = prompt
            return "## 场景一 [well-morning]\n画面：只返回了很短的一小段。"

        with patch("agents.rewrite.call_llm", side_effect=fake_call):
            result = RewriteAgent(self.book_id)._refine_dialogue(
                self.episode,
                [{"severity": "medium", "title": "dialogue thin", "suggestion": "add subtext"}],
            )

        self.assertEqual(result, "")
        self.assertIn("夜厅烛火和账册证据", captured["prompt"])
        with Session() as session:
            script = session.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == self.episode,
            ).first()
        self.assertEqual(script.content, long_script)

    def test_rewrite_agent_retries_after_invalid_non_json_output(self):
        calls = {"count": 0}

        def fake_call(prompt, system=None, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return (
                    '{ "diagnosis": { "summary": "...", "applied_rule_families": [...], "remaining_risks": [...] }, '
                    '"rewritten_script": "placeholder", "change_summary": ["x"] }\n\n'
                    "Need to think more before returning final JSON."
                )
            return json.dumps(
                {
                    "diagnosis": {
                        "summary": "retry succeeded",
                        "applied_rule_families": ["prop_evidence_continuity"],
                        "remaining_risks": [],
                    },
                    "rewritten_script": "\n".join(
                        [
                            "## 场景一 [well-morning]",
                            "画面：" + ("The monk is drenched awake and silently checks the hidden token before answering. " * 10),
                            "Monk A：Not yet.",
                            "Monk B：Answer me first.",
                            "特写：" + ("Water gathers on the token seam before he looks up. " * 8),
                            "## 场景二 [hall-night]",
                            "画面：" + ("He reveals the token and corners the others with the truth they were trying to bury. " * 10),
                            "Monk B：Who told you that?",
                            "Monk A：The hall did.",
                            "特写：" + ("The token edge flashes under the lamp. " * 8),
                        ]
                    ),
                    "change_summary": ["Retry returned valid JSON"],
                },
                ensure_ascii=False,
            )

        with patch("agents.rewrite.call_llm", side_effect=fake_call):
            output = RewriteAgent(self.book_id).run(self.episode)

        self.assertEqual(calls["count"], 2)
        rewritten = Path(output).read_text(encoding="utf-8")
        self.assertIn("corners the others", rewritten)

    def test_rewrite_agent_retries_after_short_rewritten_script_payload(self):
        calls = {"count": 0}

        def fake_call(prompt, system=None, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return json.dumps(
                    {
                        "diagnosis": {
                            "summary": "too thin",
                            "applied_rule_families": ["prop_evidence_continuity"],
                            "remaining_risks": [],
                        },
                        "rewritten_script": "placeholder",
                        "change_summary": ["not enough"],
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "diagnosis": {
                        "summary": "retry after short payload",
                        "applied_rule_families": ["prop_evidence_continuity"],
                        "remaining_risks": [],
                    },
                    "rewritten_script": "\n".join(
                        [
                            "## 场景一 [well-morning]",
                            "画面：" + ("The monk is drenched awake, checks the hidden token, and accepts the punishment. " * 10),
                            "Monk A：I can wait.",
                            "Monk B：Then wait.",
                            "特写：" + ("The hidden token presses against his sleeve fold. " * 8),
                            "## 场景二 [hall-night]",
                            "画面：" + ("He forces the others to face the token reveal and the sutra secret they buried. " * 10),
                            "Monk B：You came back for this.",
                            "Monk A：I came back for the lie behind it.",
                            "特写：" + ("The sutra edge and token corner align in the frame. " * 8),
                        ]
                    ),
                    "change_summary": ["Retry returned a full script body"],
                },
                ensure_ascii=False,
            )

        with patch("agents.rewrite.call_llm", side_effect=fake_call):
            output = RewriteAgent(self.book_id).run(self.episode)

        self.assertEqual(calls["count"], 2)
        rewritten = Path(output).read_text(encoding="utf-8")
        self.assertIn("token reveal", rewritten)

    def test_extract_script_body_prefers_latest_complete_scene_block(self):
        raw = "\n".join(
            [
                "Need repair issues first.",
                "Scene 1: draft idea",
                "more planning",
                "## 场景一 [well-morning]",
                "画面：旧版动作" * 10,
                "和尚甲：旧版台词" * 5,
                "## 场景二 [courtyard-day]",
                "特写：旧版证据" * 10,
                "和尚乙：旧版台词" * 5,
                "random note",
                "## 场景一 [well-morning]",
                "画面：正式版场景一动作" * 10,
                "和尚甲：正式版场景一台词" * 5,
                "## 场景二 [courtyard-day]",
                "特写：正式版场景二证据" * 10,
                "和尚乙：正式版场景二台词" * 5,
                "## 场景三 [kitchen-dusk]",
                "画面：正式版场景三动作" * 10,
                "和尚丙：正式版场景三台词" * 5,
                "## 场景四 [room-night]",
                "特写：正式版场景四证据" * 10,
                "和尚甲：正式版场景四台词" * 5,
            ]
        )

        extracted = RewriteAgent(self.book_id)._extract_script_body(raw)

        self.assertTrue(extracted.startswith("## 场景一 [well-morning]"))
        self.assertIn("正式版场景三", extracted)
        self.assertNotIn("Need repair issues first.", extracted)

    def test_extract_script_body_removes_trailing_meta_sections(self):
        raw = "\n".join(
            [
                "## 场景一 [well-morning]",
                "画面：井边动作。" * 16,
                "和尚甲：别急，我先看清这块牌子，再决定要不要开口。" * 5,
                "## 场景二 [hall-night]",
                "特写：法牌边角沾水。" * 16,
                "和尚乙：你刚才到底藏了什么，为什么每次都只差一步让我抓住？" * 5,
                "## 剧集设定",
                "这是后置说明，不应进入最终剧本。",
            ]
        )

        extracted = RewriteAgent(self.book_id)._extract_script_body(raw)

        self.assertIn("## 场景二 [hall-night]", extracted)
        self.assertNotIn("## 剧集设定", extracted)
        self.assertNotIn("这是后置说明", extracted)

    def test_extract_script_body_accepts_chinese_scene_headers_without_brackets(self):
        raw = "\n".join(
            [
                "## 剧集设定",
                "这是辅助说明。",
                "### 场景一 · 寺庙水房·清晨",
                "画面：" + ("冷水泼下，门槛潮湿。" * 20),
                "和尚甲：师兄，我没偷。",
                "和尚乙：嘴硬没有用。",
                "特写：" + ("袖口水痕贴着木牌边角。" * 14),
                "### 场景二 · 库房·入夜",
                "画面：" + ("油灯发颤，旧供台靠墙。" * 20),
                "和尚丙：别把我也拖下水。",
                "和尚甲：你刚才故意没绑紧。",
                "特写：" + ("铜丝从袖口滑进掌心。" * 14),
            ]
        )

        extracted = RewriteAgent(self.book_id)._extract_script_body(raw)

        self.assertTrue(extracted.startswith("## 场景一 · 寺庙水房·清晨"))
        self.assertIn("## 场景二 · 库房·入夜", extracted)
        self.assertNotIn("## 剧集设定", extracted)

    def test_extract_script_body_skips_auxiliary_sections_after_scene_blocks(self):
        raw = "\n".join(
            [
                "### 场景一 · 寺庙水房·清晨",
                "画面：" + ("水房门被踹开，木桶撞地。" * 18),
                "和尚甲：我没碰那块牌子。",
                "和尚乙：牌从你脚边出来，就是你的。",
                "特写：" + ("湿泥里法牌边角发亮。" * 12),
                "## 情绪点标注",
                "- 这一段不应进入剧本。",
                "## 场景二 · 库房·入夜",
                "画面：" + ("绳结松动，油灯压低。" * 18),
                "和尚丙：你出去可以，别连累我。",
                "和尚甲：我只取该取的证据。",
                "特写：" + ("旧供台底座裂缝露出铜钉。" * 12),
                "## 场景二信息钩子",
                "- 这也是辅助说明。",
            ]
        )

        extracted = RewriteAgent(self.book_id)._extract_script_body(raw)

        self.assertIn("## 场景一 · 寺庙水房·清晨", extracted)
        self.assertIn("## 场景二 · 库房·入夜", extracted)
        self.assertNotIn("## 情绪点标注", extracted)
        self.assertNotIn("信息钩子", extracted)

    def test_normalize_dialogue_format_splits_inline_narrative_quotes(self):
        agent = RewriteAgent(self.book_id)
        normalized = agent._normalize_dialogue_format(
            "\n".join(
                [
                    "## 场景一 [well-morning]",
                    "画面：井边一桶冷水泼下。",
                    "和尚乙从门外逆光走进，声音不高不低：“寺里规矩，先醒醒脑。”",
                    "乙的视线在墙根停了一瞬，又移开：“睡死了。”",
                ]
            )
        )

        self.assertIn("和尚乙从门外逆光走进，声音不高不低。", normalized)
        self.assertIn("和尚乙：寺里规矩，先醒醒脑。", normalized)
        self.assertIn("乙的视线在墙根停了一瞬，又移开。", normalized)
        self.assertIn("乙：睡死了。", normalized)

    def test_load_expected_scene_names_prefers_current_script_headers_over_outline(self):
        agent = RewriteAgent(self.book_id)
        agent._episode_outline = {"scenes": ["住处", "旧场景"]}
        agent._current_script_content = "\n".join(
            [
                "## 场景一 [寺庙水房]",
                "画面：冷水兜头泼下。",
                "## 场景二 [库房]",
                "画面：门闩落下，油灯一晃。",
            ]
        )

        names = agent._load_expected_scene_names()

        self.assertEqual(names, ["寺庙水房", "库房"])

    def test_forced_scaffold_prompt_requires_exact_scene_blocks(self):
        agent = RewriteAgent(self.book_id)
        agent._skill_block = "skill"
        agent._foundation_block = "foundation"
        agent._execution_plan_block = "plan"
        agent._repair_packet_block = "packet"
        agent._current_script_content = self.script_text
        agent._expected_scene_names = ["well-morning", "hall-night"]

        prompt = agent._build_forced_scaffold_prompt("invalid")

        self.assertIn("Forced Scaffold Rewrite Task", prompt)
        self.assertIn("Write exactly the planned scene blocks", prompt)
        self.assertIn("Each scene must contain one `画面：` block", prompt)
        self.assertIn("Never leave the last scene truncated.", prompt)
        self.assertIn("The first line must be the first scaffold scene header exactly.", prompt)
        self.assertIn("## 场景一 [well-morning]", prompt)
        self.assertIn("角色甲：台词", prompt)
        self.assertNotIn("【疑点/反转点：】", prompt)

    def test_extract_salvage_hints_keeps_repair_signal_from_invalid_output(self):
        raw = "\n".join(
            [
                "Need answer JSON.",
                "1. scene-2 scripture appears without a transition beat - add a bridge shot explaining how the character got the scripture.",
                "2. Keep character dialogue aligned with visible state before hidden truth surfaces.",
                "Return only valid JSON.",
            ]
        )

        hints = RewriteAgent(self.book_id)._extract_salvage_hints(raw)

        self.assertIn("transition beat", hints)
        self.assertIn("visible state", hints)
        self.assertNotIn("Return only valid JSON", hints)

    def test_detects_analysis_only_fallback_output(self):
        raw = "\n".join(
            [
                "The user wants me to repair the episode script under the Production Skill constraints.",
                "Let me analyze the current script.",
                "The current script is incomplete.",
                "Issues to repair:",
                "1. Fix the hook.",
            ]
        )

        self.assertTrue(RewriteAgent(self.book_id)._looks_like_analysis_only_output(raw))

    def test_compact_json_fallback_prompt_requires_braced_json_response(self):
        agent = RewriteAgent(self.book_id)
        agent._expected_scene_names = ["well-morning", "hall-night"]
        agent._repair_packet_block = "packet"
        agent._current_script_content = self.script_text
        agent._fallback_salvage_hints = "- keep prop continuity\n- restore visible trigger"
        agent._latest_qa_issues = [
            {
                "title": "prop chain broken",
                "location": {"script_section": "scene-2"},
                "description": "token handoff missing",
            }
        ]

        prompt = agent._build_compact_json_fallback_prompt()

        self.assertIn("The first non-whitespace character of your response must be `{`", prompt)
        self.assertIn("Expected scene sequence: well-morning, hall-night", prompt)
        self.assertIn("## Priority Repair Focus", prompt)
        self.assertIn("prop chain broken @ scene-2", prompt)
        self.assertIn("## Salvaged Repair Hints", prompt)
        self.assertIn("Do not restate the task.", prompt)

    def test_script_only_fallback_prompt_mentions_stage_and_scene_agendas(self):
        agent = RewriteAgent(self.book_id)
        agent._skill_block = "skill"
        agent._foundation_block = "foundation"
        agent._execution_plan_block = "plan"
        agent._repair_packet_block = "packet"
        agent._current_script_content = self.script_text
        agent._expected_scene_names = ["well-morning", "hall-night"]
        agent._fallback_salvage_hints = ""

        prompt = agent._build_script_only_fallback_prompt()

        self.assertIn("Follow `stage_repair_agenda` in order", prompt)
        self.assertIn("scene_repair_agenda", prompt)

    def test_compiler_rebuild_prompt_uses_stage_and_scene_agendas_as_primary_source(self):
        agent = RewriteAgent(self.book_id)
        agent._skill_block = "skill"
        agent._foundation_block = "foundation"
        agent._execution_plan_block = "plan"
        agent._repair_packet_block = "packet"
        agent._current_script_content = self.script_text
        agent._expected_scene_names = ["well-morning", "hall-night"]

        prompt = agent._build_compiler_rebuild_prompt()

        self.assertIn("Compiler Rebuild Task", prompt)
        self.assertIn("Use `story_fact_sheet`, `stage_repair_agenda`, and `scene_repair_agenda` as the primary source of truth", prompt)
        self.assertIn("If the current draft contains stale beats that conflict with the repair agenda, replace them", prompt)

    def test_run_script_only_fallback_uses_compiler_rebuild_before_forced_scaffold(self):
        agent = RewriteAgent(self.book_id)
        agent._skill_block = "skill"
        agent._foundation_block = "foundation"
        agent._execution_plan_block = "plan"
        agent._repair_packet_block = "packet"
        agent._current_script_content = self.script_text
        agent._expected_scene_names = ["well-morning", "hall-night"]
        agent._book_title = self.book_title
        agent._episode = self.episode

        rebuilt_script = "\n".join(
            [
                "## 场景一 [well-morning]",
                "画面：井边水花四溅，旧桶撞在青石地上。" * 8,
                "和尚甲：先别碰那块牌子，我看到的东西还没说完。" * 4,
                "和尚乙：今天这摊事别都推给我，我只是照规矩把人带过来。" * 4,
                "特写：旧法牌沾着水，掌印停在木纹上不再扩散。" * 6,
                "## 场景二 [hall-night]",
                "画面：夜厅烛火晃动，门闩和供台阴影一前一后压在墙上。" * 8,
                "和尚甲：我现在不喊人，是因为还差最后一眼能翻盘的证据。" * 4,
                "和尚丙：你再往前一步，我就知道你到底想把谁拖下水。" * 4,
                "特写：供台边缘的暗红纤维和袖口残线在同一束灯光里并排。" * 6,
            ]
        )

        with patch("agents.rewrite.call_llm", side_effect=["analysis only", rebuilt_script]) as mocked_call:
            rewritten, report = agent._run_script_only_fallback("system")

        self.assertEqual(mocked_call.call_count, 2)
        self.assertTrue(rewritten.startswith("## 场景一"))
        self.assertIn("Recovered a full rewritten episode", report["change_summary"][0])

    def test_build_compact_issue_focus_block_limits_to_latest_qa_items(self):
        agent = RewriteAgent(self.book_id)
        agent._latest_qa_issues = [
            {"title": f"issue-{index}", "location": {"script_section": f"scene-{index}"}, "description": "desc"}
            for index in range(1, 8)
        ]

        block = agent._build_compact_issue_focus_block()

        self.assertIn("## Priority Repair Focus", block)
        self.assertIn("issue-1 @ scene-1", block)
        self.assertIn("issue-5 @ scene-5", block)
        self.assertNotIn("issue-6 @ scene-6", block)

    def test_call_structured_rewrite_jumps_to_compact_json_after_analysis_only_output(self):
        agent = RewriteAgent(self.book_id)
        agent._current_script_content = self.script_text
        agent._skill_block = "skill"
        agent._foundation_block = "foundation"
        agent._generation_brief_block = "brief"
        agent._execution_plan_block = "plan"
        agent._repair_packet_block = "packet"
        agent._expected_scene_names = ["well-morning", "hall-night"]
        agent._latest_qa_issues = [{"title": "prop chain broken", "description": "token handoff missing"}]
        agent._book_title = self.book_title
        agent._episode = self.episode

        compact_json = json.dumps(
            {
                "diagnosis": {"summary": "compact recovery"},
                "rewritten_script": "\n".join(
                    [
                        "## 场景一 [well-morning]",
                        "画面：" + ("井边动作" * 24),
                        "和尚甲：先别急，我还没把看到的东西说完。",
                        "和尚乙：这里轮不到你拖时间。",
                        "特写：" + ("法牌边角冷光" * 16),
                        "## 场景二 [hall-night]",
                        "画面：" + ("夜厅动作" * 24),
                        "和尚甲：你们把它放错了地方，也露了不该露的手法。",
                        "和尚丙：你今晚要是敢出去，就别怪我不客气。",
                        "特写：" + ("绳尾结扣特写" * 16),
                    ]
                ),
                "change_summary": ["compact path succeeded"],
            },
            ensure_ascii=False,
        )

        with patch("agents.rewrite.call_llm", side_effect=["The user wants me to repair this script.\nLet me analyze the current script first.", compact_json]) as mocked_call:
            rewritten, report = agent._call_structured_rewrite("prompt", "system")

        self.assertEqual(mocked_call.call_count, 2)
        self.assertTrue(rewritten.startswith("## 场景一"))
        self.assertEqual(report["change_summary"][0], "compact path succeeded")

    def test_run_script_only_fallback_uses_forced_scaffold_after_two_invalid_attempts(self):
        agent = RewriteAgent(self.book_id)
        agent._skill_block = "skill"
        agent._foundation_block = "foundation"
        agent._execution_plan_block = "plan"
        agent._repair_packet_block = "packet"
        agent._current_script_content = self.script_text
        agent._expected_scene_names = ["well-morning", "hall-night"]
        agent._book_title = self.book_title
        agent._episode = self.episode

        forced_script = "\n".join(
            [
                "## 场景一 [well-morning]",
                "画面：井边水花四溅，旧桶撞在青石地上。" * 8,
                "和尚甲：先别碰那块牌子，我看到的东西还没说完。" * 4,
                "和尚乙：你一个挂单和尚，哪来的胆子在这儿指手画脚。" * 4,
                "特写：旧法牌沾着水，掌印停在木纹上不再扩散。" * 6,
                "## 场景二 [hall-night]",
                "画面：烛火在梁角发颤，湿账页摊开后只剩第三页留着暗红指印。" * 8,
                "和尚甲：昨夜那只手我没出声，是怕打草惊蛇，也是怕自己先死在门后。" * 4,
                "和尚丙：你到底还知道多少，为什么每一步都像早就算过。" * 4,
                "特写：账页上的指印停在第三页，断缺的尾指位置和白骨缺口完全吻合。" * 6,
            ]
        )

        with patch("agents.rewrite.call_llm", side_effect=["analysis only", "still analysis", forced_script]):
            rewritten, report = agent._run_script_only_fallback("system")

        self.assertTrue(rewritten.startswith("## 场景一"))
        self.assertIn("第三页", rewritten)
        self.assertIn("Recovered a full rewritten episode", report["change_summary"][0])

    def test_run_script_only_fallback_skips_normalization_when_raw_is_analysis_only(self):
        agent = RewriteAgent(self.book_id)
        agent._skill_block = "skill"
        agent._foundation_block = "foundation"
        agent._execution_plan_block = "plan"
        agent._repair_packet_block = "packet"
        agent._current_script_content = self.script_text
        agent._expected_scene_names = ["well-morning", "hall-night"]
        agent._book_title = self.book_title
        agent._episode = self.episode

        analysis_only = "\n".join(
            [
                "The user wants me to repair the episode script under the Production Skill constraints.",
                "Let me analyze the current script.",
                "The current script is incomplete.",
                "Issues to repair:",
            ]
        )
        forced_script = "\n".join(
            [
                "## 场景一 [well-morning]",
                "画面：井边水声骤起，木桶撞开半扇门。" * 8,
                "和尚甲：先别碰法牌，我还没把看见的东西说完。" * 4,
                "和尚乙：你跪在这里，就先按寺规把话说清楚。" * 4,
                "特写：法牌边角的旧蜡在门光里发暗。" * 6,
                "## 场景二 [hall-night]",
                "画面：柴房里烛火发抖，草堆阴影压在墙根。" * 8,
                "和尚甲：我现在不喊人，不是怕你们，是还没拿到能翻案的东西。" * 4,
                "和尚丙：你再多走一步，我就知道你到底在找什么。" * 4,
                "特写：墙根布条的断口和法牌旧绳头留下的纤维方向完全一致。" * 6,
            ]
        )

        with patch("agents.rewrite.call_llm", side_effect=[analysis_only, forced_script]) as mocked_call:
            rewritten, report = agent._run_script_only_fallback("system")

        self.assertEqual(mocked_call.call_count, 2)
        self.assertTrue(rewritten.startswith("## 场景一"))
        self.assertIn("Recovered a full rewritten episode", report["change_summary"][0])

    def test_extract_compound_fenced_script_stitches_fragmented_screenplay_blocks(self):
        raw = "\n".join(
            [
                "analysis first",
                "```text",
                "## 场景一 [well-morning]\n\n画面：半桶水泼下。\n和尚乙：今天这活谁爱干谁干。",
                "```",
                "```text",
                "和尚甲：你们看过法牌背面吗？\n特写：法牌背面浮出血指印。",
                "```",
                "```text",
                "【情绪点：受压→反制】\n【疑点/反转点：法牌为何在甲身上？】",
                "```",
                "```text",
                "## 场景二 [room-night]\n画面：住处里烛火摇晃。\n和尚丙：明天查起来，就都推到他头上。\n和尚甲：我已经死过一次了。",
                "```",
            ]
        )

        agent = RewriteAgent(self.book_id)
        agent._expected_scene_names = ["well-morning", "room-night"]
        stitched = agent._extract_compound_fenced_script(raw)

        self.assertIsNotNone(stitched)
        self.assertIn("## 场景一 [well-morning]", stitched)
        self.assertIn("## 场景二 [room-night]", stitched)
        self.assertIn("我已经死过一次了", stitched)

    def test_validate_rewrite_payload_normalizes_markdown_scene_headers(self):
        payload = {
            "diagnosis": {"summary": "ok"},
            "rewritten_script": "\n".join(
                [
                    "### 场景一 [well-morning]",
                    "画面：老井边动作" * 20,
                    "和尚甲：先忍着，我还没看到最后一步。",
                    "和尚乙：今天轮不到你做主。",
                    "特写：旧牌边缘反光" * 10,
                    "### 场景二 [hall-night]",
                    "画面：夜厅里的脚步回声" * 18,
                    "特写：法牌与血印" * 20,
                    "和尚乙：你到底看见了什么？",
                    "和尚甲：看见你们没藏干净的东西。",
                ]
            ),
            "change_summary": ["normalized headers"],
        }

        rewritten, report = RewriteAgent(self.book_id)._validate_rewrite_payload(payload)

        self.assertTrue(rewritten.startswith("## 场景一"))
        self.assertIn("## 场景二", rewritten)
        self.assertEqual(report["change_summary"][0], "normalized headers")

    def test_validate_rewrite_payload_strips_non_screenplay_sections(self):
        payload = {
            "diagnosis": {"summary": "ok"},
            "rewritten_script": "\n".join(
                [
                    "## 剧集设定",
                    "- some notes",
                    "## 场景一 [well-morning]",
                    "画面：井边动作" * 18,
                    "和尚甲：先别开口。",
                    "特写：旧牌子边缘" * 12,
                    "## 场景二 [hall-night]",
                    "画面：夜里动作" * 18,
                    "和尚乙：你到底藏了什么？",
                    "特写：袖口里的细线" * 12,
                    "## 关键资产表",
                    "- token",
                ]
            ),
            "change_summary": ["normalized headers"],
        }

        agent = RewriteAgent(self.book_id)
        agent._expected_scene_names = ["well-morning", "hall-night"]
        rewritten, _report = agent._validate_rewrite_payload(payload)

        self.assertTrue(rewritten.startswith("## 场景一 [well-morning]"))
        self.assertNotIn("## 剧集设定", rewritten)
        self.assertNotIn("## 关键资产表", rewritten)

    def test_validate_rewrite_payload_strips_scene_meta_lines_inside_screenplay(self):
        payload = {
            "diagnosis": {"summary": "ok"},
            "rewritten_script": "\n".join(
                [
                    "## 场景一 [well-morning]",
                    "**场景目的**：建立压迫。",
                    "**信息增量**：发现旧法牌。",
                    "画面：井边动作" * 18,
                    "和尚甲：先别开口。",
                    "特写：旧牌子边缘" * 12,
                    "---",
                    "## 场景二 [hall-night]",
                    "**情绪增量**：甲转为冷静。",
                    "画面：夜里动作" * 18,
                    "和尚乙：你到底藏了什么？",
                    "特写：袖口里的细线" * 12,
                ]
            ),
            "change_summary": ["normalized headers"],
        }

        agent = RewriteAgent(self.book_id)
        agent._expected_scene_names = ["well-morning", "hall-night"]
        rewritten, _report = agent._validate_rewrite_payload(payload)

        self.assertTrue(rewritten.startswith("## 场景一 [well-morning]"))
        self.assertNotIn("**场景目的**", rewritten)
        self.assertNotIn("**信息增量**", rewritten)
        self.assertNotIn("**情绪增量**", rewritten)
        self.assertNotIn("---", rewritten)

    def test_validate_rewrite_payload_strips_scene_annotation_lines_inside_screenplay(self):
        payload = {
            "diagnosis": {"summary": "ok"},
            "rewritten_script": "\n".join(
                [
                    "## 场景一 [well-morning]",
                    "画面：井边动作" * 18,
                    "和尚甲：先别开口。",
                    "【情绪点：受压→反制】",
                    "特写：旧牌子边缘" * 12,
                    "【疑点/反转点：法牌为何在甲身上？】",
                    "## 场景二 [hall-night]",
                    "画面：夜里动作" * 18,
                    "和尚乙：你到底藏了什么？",
                    "【疑点：袖口里的细线来自哪里？】",
                    "特写：袖口里的细线" * 12,
                ]
            ),
            "change_summary": ["normalized headers"],
        }

        agent = RewriteAgent(self.book_id)
        agent._expected_scene_names = ["well-morning", "hall-night"]
        rewritten, _report = agent._validate_rewrite_payload(payload)

        self.assertTrue(rewritten.startswith("## 场景一 [well-morning]"))
        self.assertNotIn("【情绪点：", rewritten)
        self.assertNotIn("【疑点/反转点：", rewritten)
        self.assertNotIn("【疑点：", rewritten)

    def test_validate_rewritten_script_rejects_incomplete_scene_blocks(self):
        agent = RewriteAgent(self.book_id)
        agent._expected_scene_names = ["well-morning", "hall-night"]

        with self.assertRaisesRegex(ValueError, "incomplete or placeholder-like scene blocks|planning/meta fragment"):
            agent._validate_rewritten_script_text(
                "\n".join(
                    [
                        "## 场景一 [well-morning]",
                        "画面：井边有水，木桶湿冷，绳影晃动。" * 12,
                        "和尚甲：先等等，我还没把话说完，你们现在看到的还只是表面。" * 6,
                        "和尚乙：少拖时间，跪着的人没有资格挑什么时候开口。" * 5,
                        "特写：桶边反光里只看见一角旧牌子，水珠顺着木纹往下滑。" * 10,
                        "## 场景二 [hall-night]",
                        "现在开始起草完整剧本",
                    ]
                ),
                strict_screenplay=True,
            )

    def test_parse_rewrite_payload_prefers_top_level_contract(self):
        raw = json.dumps(
            {
                "diagnosis": {"summary": "top level"},
                "rewritten_script": "## 场景一 [well-morning]\n画面：" + ("动作" * 40),
                "change_summary": ["kept contract"],
            },
            ensure_ascii=False,
        )
        raw = raw + "\n" + json.dumps({"summary": "inner only"}, ensure_ascii=False)

        payload = RewriteAgent(self.book_id)._parse_rewrite_payload(raw)

        self.assertEqual(payload["diagnosis"]["summary"], "top level")
        self.assertIn("rewritten_script", payload)

    def test_salvage_rewrite_payload_recovers_truncated_script_string(self):
        raw = (
            '{'
            '"diagnosis":{"summary":"rescued"},'
            '"rewritten_script":"## 场景一 [well-morning]\\n画面：' + ("动作" * 60)
            + '\\n和尚甲：先忍住。\\n## 场景二 [hall-night]\\n特写：' + ("血印" * 60)
            + '",'
            '"change_summary":["rescued"]'
        )

        payload = RewriteAgent(self.book_id)._salvage_rewrite_payload(raw)

        self.assertIsNotNone(payload)
        self.assertIn("## 场景二", payload["rewritten_script"])
        self.assertEqual(payload["diagnosis"]["summary"], "rescued")


if __name__ == "__main__":
    unittest.main()
