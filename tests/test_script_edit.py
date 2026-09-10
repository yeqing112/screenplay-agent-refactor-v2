import unittest

from core.script_beat import build_script_beats
from core.script_edit import apply_edits, validate_edits


SCRIPT = "\n".join([
    "## 场景1：钟楼外景",
    "",
    "**[开场]**",
    "",
    "林晚站在铁门前。",
    "",
    "**林晚**：",
    "“就这儿？”",
    "",
    "**[场景结束]**",
])


class ScriptEditTests(unittest.TestCase):
    def setUp(self):
        self.beats = build_script_beats(SCRIPT, episode=1)
        self.frozen = {b.beat_id: b.fingerprint for b in self.beats}

    def test_valid_replace_passes_validation(self):
        result = validate_edits(
            SCRIPT, 1,
            [{"op": "replace", "beat_id": "ep1-s1-b03", "new_text": "**林晚**：\n“这地方……”"}],
            frozen_beats=self.frozen,
        )
        self.assertTrue(result["valid"], result["conflicts"])
        self.assertEqual(result["conflicts"], [])

    def test_noop_replace_is_rejected(self):
        result = validate_edits(
            SCRIPT, 1,
            [{"op": "replace", "beat_id": "ep1-s1-b03", "new_text": "**林晚**：\n“就这儿？”"}],
            frozen_beats=self.frozen,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("no-op" in c for c in result["conflicts"]))

    def test_unknown_beat_and_structural_beat_are_rejected(self):
        result = validate_edits(
            SCRIPT, 1,
            [
                {"op": "replace", "beat_id": "ep1-s1-b99", "new_text": "x"},
                {"op": "delete", "beat_id": "ep1-s1-b04"},  # [场景结束]
            ],
            frozen_beats=self.frozen,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("不存在" in c for c in result["conflicts"]))
        self.assertTrue(any("结构标记" in c for c in result["conflicts"]))

    def test_same_beat_conflict_is_rejected(self):
        result = validate_edits(
            SCRIPT, 1,
            [
                {"op": "replace", "beat_id": "ep1-s1-b03", "new_text": "A"},
                {"op": "delete", "beat_id": "ep1-s1-b03"},
            ],
            frozen_beats=self.frozen,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("冲突" in c for c in result["conflicts"]))

    def test_apply_preserves_structure_and_replace_at_beat(self):
        new_content, applied = apply_edits(
            SCRIPT, 1,
            [{"op": "replace", "beat_id": "ep1-s1-b03", "new_text": "**林晚**：\n“这地方不对劲。”"}],
        )
        self.assertIn("“这地方不对劲。”", new_content)
        self.assertIn("**[场景结束]**", new_content)  # structure preserved
        self.assertIn("## 场景1：钟楼外景", new_content)
        self.assertEqual(applied, ["replace ep1-s1-b03"])

    def test_apply_insert_and_delete(self):
        new_content, applied = apply_edits(
            SCRIPT, 1,
            [
                {"op": "insert_after", "beat_id": "ep1-s1-b02", "new_text": "她犹豫了片刻。"},
                {"op": "delete", "beat_id": "ep1-s1-b03"},
            ],
        )
        self.assertEqual(applied, ["insert_after ep1-s1-b02", "delete ep1-s1-b03"])
        self.assertIn("她犹豫了片刻。", new_content)
        self.assertNotIn("“就这儿？”", new_content)

    def test_replace_rejected_when_new_text_repeats_sibling_beats(self):
        dup_script = "\n".join([
            "## 场景1",
            "",
            "老周提着工具箱从阴影里走出来，脚步声在空荡的钟楼里回响。",
            "",
            "林晚站在斑驳的铁门前，静静环顾四周，指尖轻轻划过生锈的门框。",
        ])
        beats = build_script_beats(dup_script, episode=1)
        frozen = {b.beat_id: b.fingerprint for b in beats}
        # Replace b01 with text that quotes b02's whole sentence (>=18 chars).
        result = validate_edits(
            dup_script, 1,
            [{"op": "replace", "beat_id": beats[0].beat_id, "new_text": "林晚站在斑驳的铁门前，静静环顾四周，指尖轻轻划过生锈的门框。她攥紧了清单。"}],
            frozen_beats=frozen,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("重复内容" in c for c in result["conflicts"]))


if __name__ == "__main__":
    unittest.main()
