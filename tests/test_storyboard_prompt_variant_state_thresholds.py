import unittest

from api.server import _build_prompt_compiler_diagnostics


class StoryboardPromptVariantStateThresholdTests(unittest.TestCase):
    def test_character_variant_state_allows_natural_partial_rephrase(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "古代寺庙院落正午烈日下，和尚甲挑着扁担走入院中，灰褐僧袍斜披露右肩，后背与前襟已被汗水湿透贴身，裤脚微湿，布鞋沾泥。"
            "他剃度光头无发，头皮被汗水打亮并沾着薄尘，额头都是汗，脸颊晒得发红，鼻翼微汗，嘴唇干燥起皮，整个人显出烈日劳作后的疲惫粗粝感。",
            "镜头缓慢推近，保持首帧角色、服装、场景与道具一致。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "character",
                        "asset_id": "433",
                        "asset_name": "和尚甲",
                        "variant_scope": "shot_variant",
                        "authority_prompt_parts": [
                            {"key": "refined_outfit", "text": "灰色或褐色棉麻僧袍斜披袈裟露右肩，后背与前襟被汗水湿透贴身，腰间束带勒紧，布鞋沾泥，裤脚微湿"},
                            {"key": "hair_style", "text": "剃度光头，无发，头皮被汗水打亮，夹杂少量灰尘"},
                            {"key": "makeup_spec", "text": "头皮与额头布满汗水和薄尘，脸颊有细小水珠与晒后泛红，鼻翼微汗，嘴唇干燥起皮，整体呈烈日劳作后的疲惫粗粝质感"},
                        ],
                    }
                ],
                "reference_images": [],
            },
            [],
        )

        check = next(check for check in diagnostics["checks"] if check["key"] == "character_variant_state")
        self.assertTrue(check["passed"])

    def test_character_variant_state_allows_reordered_chinese_state_phrases(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "\u5bfa\u5e99\u9662\u843d\u5185\u9752\u77f3\u677f\u94fa\u5c31\u7684\u9053\u8def\u4e0a\uff0c\u6b63\u5348\u70c8\u65e5\u5f3a\u70c8\uff0c\u5149\u5f71\u6591\u9a73\u3002\u4e00\u4e2a\u9752\u5e74\u5149\u5934\u548c\u5c1a\uff0c\u4e2d\u7b49\u4f53\u578b\uff0c\u8eab\u7a7f\u6e7f\u900f\u7684\u7070\u8272\u68c9\u9ebb\u50e7\u888d\uff0c\u659c\u62ab\u8888\u88df\u9732\u51fa\u53f3\u80a9\uff0c\u989d\u5934\u8138\u988a\u6709\u6c34\u73e0\u548c\u5c18\u571f\u75d5\u8ff9\uff0c\u9f3b\u7ffc\u5fae\u6c57\uff0c\u5634\u5507\u5e72\u71e5\u8d77\u76ae\u3002\u4ed6\u505c\u4e0b\u811a\u6b65\uff0c\u624b\u4e2d\u63d0\u7740\u4e00\u4e2a\u6728\u8d28\u6c34\u6876\uff0c\u6876\u8eab\u6643\u52a8\uff0c\u6c34\u4ece\u6876\u53e3\u6d12\u51fa\u6e85\u5728\u9752\u77f3\u677f\u4e0a\u3002",
            "\u955c\u5934\u4ece\u6728\u6876\u548c\u6d12\u51fa\u7684\u6c34\u5f00\u59cb\uff0c\u5411\u4e0a\u7f13\u6162\u503e\u659c\uff0c\u8ddf\u968f\u548c\u5c1a\u7532\u505c\u4f4f\u811a\u6b65\u65f6\u8eab\u4f53\u7684\u7ec6\u5fae\u6643\u52a8\uff0c\u7ed3\u675f\u4e8e\u6e7f\u900f\u540e\u80cc\u7684\u7279\u5199\u3002",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "character",
                        "asset_id": "char-shot-6",
                        "asset_name": "\u548c\u5c1a\u7532",
                        "variant_scope": "shot_variant",
                        "authority_prompt_parts": [
                            {"key": "refined_outfit", "text": "\u7070\u8272\u50e7\u888d\u540e\u80cc\u88ab\u6c57\u6c34\u6e7f\u900f\uff0c\u5e03\u6599\u7d27\u7d27\u8d34\u5728\u80cc\u810a\u4e0e\u80a9\u80db\u4e0a\uff0c\u659c\u62ab\u8888\u88df\u4ecd\u9732\u53f3\u80a9\uff0c\u888d\u6446\u4e0b\u7aef\u8fd8\u6b8b\u7559\u6e7f\u75d5"},
                            {"key": "hair_style", "text": "\u5149\u5934\u5934\u76ae\u5e03\u6ee1\u6c57\u73e0\uff0c\u5934\u9876\u53cd\u5149\u660e\u663e\uff0c\u53ef\u89c1\u5c11\u91cf\u7070\u5c18\u9644\u7740"},
                            {"key": "makeup_spec", "text": "\u867d\u662f\u80cc\u90e8\u7279\u5199\uff0c\u4f46\u53ef\u4ece\u9888\u4fa7\u548c\u8033\u540e\u770b\u51fa\u6c57\u6c34\u548c\u70ed\u6c14\u84b8\u51fa\u7684\u75b2\u60eb\u611f\uff0c\u6e7f\u900f\u5e03\u6599\u4e0b\u80a9\u80db\u808c\u8089\u7d27\u7ef7\uff0c\u900f\u51fa\u538b\u6291\u548c\u786c\u6491"},
                            {"key": "canonical_accessories", "text": "\u6728\u6876\u63d0\u628a\u5c06\u529b\u9053\u4f20\u56de\u80cc\u90e8\uff0c\u8155\u90e8\u808c\u8089\u7d27\u7ef7"},
                            {"key": "canonical_scene_effects", "text": "\u5bfa\u5e99\u9662\u843d\u6b63\u5348\u5f3a\u5149\u4e0b\u7684\u8fd1\u8ddd\u7279\u5199\uff0c\u9752\u77f3\u677f\u4e0a\u7684\u6c34\u6e0d\u53cd\u5149\u4e0e\u6811\u5f71\u6591\u9a73\u540c\u65f6\u5b58\u5728"},
                        ],
                    }
                ],
                "reference_images": [],
            },
            [],
        )

        check = next(check for check in diagnostics["checks"] if check["key"] == "character_variant_state")
        self.assertTrue(check["passed"])


if __name__ == "__main__":
    unittest.main()
