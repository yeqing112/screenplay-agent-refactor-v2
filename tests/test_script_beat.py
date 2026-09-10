import unittest

from core.script_beat import build_script_beats


SAMPLE = "\n".join([
    "# 第1集 钟楼",
    "",
    "## 场景1：钟楼外景",
    "",
    "**[开场]**",
    "",
    "林晚站在钟楼铁门前，仰头看着塔楼。",
    "",
    "**林晚**（自言自语）：",
    "“就这儿？”",
    "",
    "**[人物入场]**",
    "",
    "老周从阴影里走出来。",
    "",
    "**[场景结束]**",
    "",
    "## 场景2：大厅",
    "",
    "**老周**：",
    "进来吧。",
    "",
    "**[视觉证明1：刮痕]**",
    "特写：锁扣上的刮痕。",
])


class ScriptBeatIndexTests(unittest.TestCase):
    def test_builds_expected_beats_per_scene(self):
        beats = build_script_beats(SAMPLE, episode=1)
        scene1 = [b for b in beats if b.scene_no == 1]
        scene2 = [b for b in beats if b.scene_no == 2]
        self.assertEqual(len(scene1), 6)
        self.assertEqual(len(scene2), 2)
        self.assertEqual([b.beat_id for b in scene1], [f"ep1-s1-b{i:02d}" for i in range(1, 7)])
        self.assertEqual([b.beat_id for b in scene2], ["ep1-s2-b01", "ep1-s2-b02"])
        self.assertEqual(scene1[2].kind, "dialogue")
        self.assertEqual(scene1[2].speaker, "林晚")
        self.assertEqual(scene1[0].kind, "marker")
        self.assertEqual(scene2[1].kind, "visual_proof")
        self.assertNotEqual(scene1[0].fingerprint, scene1[2].fingerprint)

    def test_beat_id_stable_under_content_edit_and_lines_recompute(self):
        original = build_script_beats(SAMPLE, episode=1)
        target = [b for b in original if b.beat_id == "ep1-s1-b03"][0]
        next_beat = [b for b in original if b.beat_id == "ep1-s1-b04"][0]
        self.assertEqual(target.fingerprint, target.fingerprint)

        # Rewrite the dialogue turn to a two-line turn (adds one line).
        edited = SAMPLE.replace(
            "**林晚**（自言自语）：\n“就这儿？”",
            "**林晚**（自言自语）：\n“就这儿？”\n她攥紧了那道泛黄的纸边。",
        )
        rebuilt = build_script_beats(edited, episode=1)
        new_target = [b for b in rebuilt if b.beat_id == "ep1-s1-b03"][0]
        new_next = [b for b in rebuilt if b.beat_id == "ep1-s1-b04"][0]
        self.assertEqual(new_target.beat_id, "ep1-s1-b03")  # id stable
        self.assertNotEqual(new_target.fingerprint, target.fingerprint)  # content changed
        self.assertGreater(new_next.start_line, next_beat.start_line)  # line number recomputed

    def test_preamble_before_first_scene_is_ignored(self):
        beats = build_script_beats(SAMPLE, episode=1)
        self.assertFalse(any(b.scene_no == 0 for b in beats))


if __name__ == "__main__":
    unittest.main()
