"""Screenwriting Libraries — 编剧维度标准化映射。

参考来源：
- Christopher Vogler: The Writer's Journey (8 archetypes + 12 stages)
- ScriptReaderPro: 6 key character archetypes
- 渐构 Modevol: Story Structure & Types (20+ plot types)
- 50个可复用故事模板 (zsc/art_story_telling)
- 中文百科: 戏剧冲突 / 戏剧情节
- 黑格尔戏剧冲突理论 / 布伦退尔冲突说
- 曹禺戏剧冲突分析

核心思想：编剧术语不应每次由 LLM 即兴生成，应使用标准化映射。
"""

# ============================================================
# 1. 角色原型库 (Character Archetypes)
# ============================================================
CHARACTER_ARCHETYPE_LIBRARY: dict[str, dict] = {
    "hero": {
        "name": "英雄",
        "name_en": "Hero",
        "source": "Vogler/荣格原型",
        "jung_equivalent": "自我 (Ego)",
        "dramatic_function": "观众认同载体，经历成长与转变",
        "core_drive": "成长、突破、领悟",
        "typical_arc": "缺陷 → 试炼 → 觉醒 → 转化",
        "variations": ["经典英雄", "反英雄", "悲剧英雄", "不情愿英雄", "催化剂英雄", "集体英雄", "日常英雄", "牺牲英雄"],
        "usage": "主角、联合主角",
    },
    "mentor": {
        "name": "导师",
        "name_en": "Mentor",
        "source": "Vogler/荣格原型",
        "jung_equivalent": "自性 (Self)",
        "dramatic_function": "教诲、推动、给予——让英雄成长",
        "core_drive": "传承智慧、促成英雄蜕变",
        "typical_arc": "给予指引 → 英雄超越 → 自身也被救赎",
        "variations": ["智慧老人", "反面导师", "暂时性导师", "内在导师（记忆/观念）"],
        "usage": "导师角色、B故事角色",
    },
    "threshold_guardian": {
        "name": "守门人",
        "name_en": "Threshold Guardian",
        "source": "Vogler/荣格原型",
        "jung_equivalent": "阴影（部分）",
        "dramatic_function": "考验英雄决心，迫使其证明价值",
        "core_drive": "阻拦、测试、筛选",
        "typical_arc": "出现阻拦 → 英雄克服 → 守门人消失/转化",
        "variations": ["物理障碍", "心理障碍", "社会规则", "信息守门人"],
        "usage": "门槛处的阻碍者",
    },
    "ally": {
        "name": "盟友",
        "name_en": "Ally",
        "source": "Vogler/荣格原型",
        "jung_equivalent": "人格面具（部分）",
        "dramatic_function": "支持英雄、交代前史、加深人性",
        "core_drive": "陪伴、帮助、见证成长",
        "typical_arc": "相遇 → 建立信任 → 共同战斗 → 各自成长",
        "variations": ["忠诚伙伴", "Comic Relief（搞笑担当）", "情报告知者", "工具提供者"],
        "usage": "配角、团队成员",
    },
    "shapeshifter": {
        "name": "变形者",
        "name_en": "Shapeshifter",
        "source": "Vogler/荣格原型",
        "jung_equivalent": "阿尼玛/阿尼姆斯",
        "dramatic_function": "制造悬念、改变力量对比、代表不确定性",
        "core_drive": "变化、暧昧、忠诚不确定",
        "typical_arc": "神秘出现 → 立场不明 → 揭示真实立场 → 关键时刻站队",
        "variations": ["爱情对象", "双面间谍", "道德模糊者", "伪装者"],
        "usage": "悬念制造者、爱情线核心",
    },
    "shadow": {
        "name": "阴影",
        "name_en": "Shadow",
        "source": "Vogler/荣格原型",
        "jung_equivalent": "阴影 (Shadow)",
        "dramatic_function": "代表英雄的黑暗面，制造核心冲突",
        "core_drive": "对抗、压制、代表英雄不愿面对的自我",
        "typical_arc": "暗中威胁 → 正面冲突 → 最终对决 → 被击败/被接纳",
        "variations": ["纯粹反派", "镜像反派（英雄的黑暗面）", "社会体制", "内心阴影"],
        "usage": "主要反派、对立面",
    },
    "trickster": {
        "name": "捣蛋鬼",
        "name_en": "Trickster",
        "source": "Vogler/荣格原型",
        "jung_equivalent": "本我 (Id)",
        "dramatic_function": "打破规则、制造混乱、揭示真相、带来欢乐",
        "core_drive": "颠覆秩序、制造幽默、推动变革",
        "typical_arc": "出现搅局 → 制造混乱 → 意外推动剧情 → 提供新视角",
        "variations": ["喜剧担当", "讽刺者", "颠覆者", "意外真相揭示者"],
        "usage": "喜剧角色、讽刺工具",
    },
    "herald": {
        "name": "信使",
        "name_en": "Herald",
        "source": "Vogler/荣格原型",
        "jung_equivalent": "直觉功能",
        "dramatic_function": "带来冒险召唤，宣告故事开始",
        "core_drive": "传递信息、预示变化",
        "typical_arc": "出现传信 → 引发英雄行动 → 使命完成",
        "variations": ["物理信使", "事件触发者", "预兆/梦境"],
        "usage": "开场触发者",
    },
}

# ============================================================
# 2. 故事结构库 (Story Structure Templates)
# ============================================================
STORY_STRUCTURE_LIBRARY: dict[str, dict] = {
    "three_act": {
        "name": "三幕式结构",
        "name_en": "Three-Act Structure",
        "source": "亚里士多德 / 好莱坞标准",
        "stages": [
            {"name": "第一幕：铺陈", "function": "建立世界、角色、冲突点"},
            {"name": "第二幕：对抗", "function": "障碍累积、中段转折、最大危机"},
            {"name": "第三幕：解决", "function": "高潮 + 结局"},
        ],
        "usage": "最通用的商业电影结构",
    },
    "heros_journey": {
        "name": "英雄之旅",
        "name_en": "Hero's Journey",
        "source": "坎贝尔 / 沃格勒",
        "stages": [
            {"name": "日常世界", "function": "建立英雄的平凡生活"},
            {"name": "冒险召唤", "function": "事件打破日常"},
            {"name": "拒绝召唤", "function": "英雄犹豫"},
            {"name": "遇见导师", "function": "获得指引/工具"},
            {"name": "跨越第一道门槛", "function": "进入特殊世界"},
            {"name": "考验、盟友、敌人", "function": "在新世界中学习"},
            {"name": "接近最深的洞穴", "function": "准备面对最大恐惧"},
            {"name": "磨难", "function": "面对死亡/最大危机"},
            {"name": "奖赏", "function": "获得宝物/领悟"},
            {"name": "踏上归途", "function": "带着成果返回"},
            {"name": "复活", "function": "最终考验，彻底转变"},
            {"name": "带着万灵药归来", "function": "英雄回归并分享成长"},
        ],
        "usage": "冒险/成长/奇幻叙事",
    },
    "kishotenketsu": {
        "name": "起承转合",
        "name_en": "Kishotenketsu",
        "source": "东亚四段叙事",
        "stages": [
            {"name": "起 (Ki)", "function": "开端，介绍"},
            {"name": "承 (Sho)", "function": "发展，承接"},
            {"name": "转 (Ten)", "function": "意外转折（重点）"},
            {"name": "结 (Ketsu)", "function": "收束，融合"},
        ],
        "usage": "东亚文艺/思辨/诗意叙事，不依赖二元冲突",
    },
    "freytag_pyramid": {
        "name": "弗莱塔格金字塔",
        "name_en": "Freytag's Pyramid",
        "source": "古希腊悲剧理论",
        "stages": [
            {"name": "Exposition（铺陈）", "function": "背景介绍"},
            {"name": "Rising Action（上升）", "function": "冲突累积"},
            {"name": "Climax（高潮）", "function": "最大张力点"},
            {"name": "Falling Action（下降）", "function": "后果展开"},
            {"name": "Denouement（结局）", "function": "矛盾解决"},
        ],
        "usage": "悲剧/史诗叙事",
    },
    "danharmon_story_circle": {
        "name": "丹·哈蒙故事圈",
        "name_en": "Dan Harmon's Story Circle",
        "source": "Dan Harmon（简化版英雄之旅）",
        "stages": [
            {"name": "You（你）", "function": "在舒适区"},
            {"name": "Need（需求）", "function": "感到缺失"},
            {"name": "Go（出发）", "function": "进入新世界"},
            {"name": "Search（寻找）", "function": "寻找答案"},
            {"name": "Find（找到）", "function": "获得想要的"},
            {"name": "Take（代价）", "function": "付出代价"},
            {"name": "Return（回归）", "function": "回到日常"},
            {"name": "Change（改变）", "function": "因经历而改变"},
        ],
        "usage": "短剧/单集叙事、TV episode结构",
    },
    "save_the_cat": {
        "name": "救猫咪结构",
        "name_en": "Save the Cat",
        "source": "Blake Snyder",
        "stages": [
            {"name": "Opening Image", "function": "开场画面，定调"},
            {"name": "Theme Stated", "function": "主题被说出"},
            {"name": "Set-up", "function": "建立世界/角色"},
            {"name": "Catalyst", "function": "催化剂事件"},
            {"name": "Debate", "function": "犹豫/讨论"},
            {"name": "Break into Two", "function": "进入第二幕"},
            {"name": "B Story", "function": "B故事线启动"},
            {"name": "Fun and Games", "function": "类型承诺兑现"},
            {"name": "Midpoint", "function": "中点，虚假胜利/失败"},
            {"name": "Bad Guys Close In", "function": "反派逼近"},
            {"name": "All Is Lost", "function": "一切皆失"},
            {"name": "Dark Night of the Soul", "function": "灵魂暗夜"},
            {"name": "Break into Three", "function": "进入第三幕"},
            {"name": "Finale", "function": "最终对决"},
            {"name": "Final Image", "function": "终场画面，对比开场"},
        ],
        "usage": "好莱坞商业电影标准模板",
    },
    "tsundoku": {
        "name": "积玉堆金（多线交织）",
        "name_en": "Multi-thread Weaving",
        "source": "群像剧/多线叙事",
        "stages": [
            {"name": "A线启动", "function": "主线开端"},
            {"name": "B线启动", "function": "副线开端"},
            {"name": "C线启动", "function": "第三线开端"},
            {"name": "线索交织", "function": "各线在关键点交汇"},
            {"name": "总爆发", "function": "所有线索同时引爆"},
            {"name": "收束", "function": "各线结局"},
        ],
        "usage": "群像剧、社会派叙事、多线悬疑",
    },
}

# ============================================================
# 3. 冲突类型库 (Conflict Types)
# ============================================================
CONFLICT_TYPE_LIBRARY: dict[str, dict] = {
    "person_vs_person": {
        "name": "人与人",
        "name_en": "Person vs. Person",
        "description": "两个角色直接对抗",
        "subtypes": ["意志冲突", "性格冲突", "价值观冲突", "情感冲突"],
        "usage": "最基础的戏剧冲突",
    },
    "person_vs_self": {
        "name": "人与自我",
        "name_en": "Person vs. Self",
        "description": "角色内心矛盾",
        "subtypes": ["道德困境", "身份认同危机", "理性vs情感", "过去vs现在"],
        "usage": "心理剧、成长故事",
    },
    "person_vs_society": {
        "name": "人与社会",
        "name_en": "Person vs. Society",
        "description": "个人与社会制度/规范对抗",
        "subtypes": ["阶级冲突", "体制冲突", "文化冲突", "法律冲突"],
        "usage": "社会派叙事、反乌托邦",
    },
    "person_vs_nature": {
        "name": "人与自然",
        "name_en": "Person vs. Nature",
        "description": "人对抗自然力量",
        "subtypes": ["灾难", "疾病", "荒野求生", "动物威胁"],
        "usage": "生存叙事、灾难片",
    },
    "person_vs_technology": {
        "name": "人与科技",
        "name_en": "Person vs. Technology",
        "description": "人对抗失控科技",
        "subtypes": ["AI叛变", "监控社会", "虚拟现实困境", "科技异化"],
        "usage": "科幻、反乌托邦",
    },
    "person_vs_fate": {
        "name": "人与命运",
        "name_en": "Person vs. Fate/Destiny",
        "description": "人对抗命运/预知/超自然",
        "subtypes": ["宿命论", "预言", "诅咒", "神的意志"],
        "usage": "希腊悲剧、奇幻叙事",
    },
    "person_vs_supernatural": {
        "name": "人与超自然",
        "name_en": "Person vs. Supernatural",
        "description": "人对抗超自然力量",
        "subtypes": ["鬼魂", "恶魔", "魔法", "异世界"],
        "usage": "恐怖、奇幻",
    },
}

# ============================================================
# 4. 对白风格库 (Dialogue Styles)
# ============================================================
DIALOGUE_STYLE_LIBRARY: dict[str, dict] = {
    "subtext": {
        "name": "潜台词",
        "name_en": "Subtext",
        "description": "角色言外之意，真正想表达的藏在话语之下",
        "techniques": ["一语双关", "欲言又止", "意在言外", "言简意赅", "顾左右而言他"],
        "emotion_effect": "层次丰富、真实感、让观众参与解读",
        "usage": "高端编剧标配，现实主义对白",
    },
    "direct_expression": {
        "name": "直抒胸臆",
        "name_en": "Direct Expression",
        "description": "角色直接说出内心想法",
        "techniques": ["独白", "告白", "争吵中的爆发", "临终遗言"],
        "emotion_effect": "冲击力强、情感释放、高潮时刻",
        "usage": "高潮场景、情感爆发点",
    },
    "dramatic_irony": {
        "name": "戏剧反讽",
        "name_en": "Dramatic Irony",
        "description": "观众知道而角色不知道的信息差",
        "techniques": ["观众知情", "角色无知", "信息不对称"],
        "emotion_effect": "紧张、焦虑、同情、期待",
        "usage": "悬疑、悲剧、讽刺",
    },
    "repartee": {
        "name": "机智对答",
        "name_en": "Repartee",
        "description": "快速、聪明的来回对话",
        "techniques": ["针锋相对", "双关语", "文字游戏", "以子之矛攻子之盾"],
        "emotion_effect": "机智、幽默、智力较量",
        "usage": "喜剧、爱情片、权力博弈",
    },
    "monologue": {
        "name": "独白",
        "name_en": "Monologue",
        "description": "角色单独长段讲话",
        "techniques": ["内心独白", "对观众说话", "回忆叙述", "自我辩解"],
        "emotion_effect": "深入内心、揭示真相、建立共情",
        "usage": "角色深度刻画、关键转折",
    },
    "silence": {
        "name": "沉默/停顿",
        "name_en": "Silence/Pause",
        "description": "用沉默和停顿传达情感",
        "techniques": ["长时间停顿", "欲言又止", "无言以对", "眼神交流替代台词"],
        "emotion_effect": "紧张、尴尬、深沉、无法言说的痛苦",
        "usage": "高张力场景、情感过载时刻",
    },
    "voice_over": {
        "name": "旁白",
        "name_en": "Voice-over",
        "description": "画外音叙述",
        "techniques": ["第一人称回忆", "全知视角", "讽刺评论", "内心独白外化"],
        "emotion_effect": "主观视角、回忆感、讽刺、信息传递",
        "usage": "回忆叙事、黑色电影、纪录片风格",
    },
    "verbal_combat": {
        "name": "语言交锋",
        "name_en": "Verbal Combat",
        "description": "以语言为武器的对抗",
        "techniques": ["争吵", "审讯", "辩论", "威胁", "操控"],
        "emotion_effect": "紧张、权力博弈、智力较量",
        "usage": "法庭戏、谈判、家庭矛盾",
    },
}

# ============================================================
# 5. 场景结构库 (Scene Structure)
# ============================================================
SCENE_STRUCTURE_LIBRARY: dict[str, dict] = {
    "establishing": {
        "name": "建立场景",
        "function": "交代时间、地点、人物关系",
        "typical_elements": ["环境描写", "人物出场", "氛围建立"],
        "pacing": "slow",
    },
    "inciting_incident": {
        "name": "催化事件",
        "function": "打破平衡，启动故事",
        "typical_elements": ["意外事件", "消息到达", "冲突爆发"],
        "pacing": "medium",
    },
    "rising_action": {
        "name": "上升动作",
        "function": "冲突累积，张力递增",
        "typical_elements": ["障碍增加", "赌注升高", "关系恶化"],
        "pacing": "building",
    },
    "midpoint": {
        "name": "中点",
        "function": "虚假胜利或虚假失败，方向转变",
        "typical_elements": ["转折", "揭示新信息", "目标调整"],
        "pacing": "turning",
    },
    "crisis": {
        "name": "危机",
        "function": "最大困难降临，英雄面临最大考验",
        "typical_elements": ["两难抉择", "失去重要东西", "盟友背叛"],
        "pacing": "intense",
    },
    "climax": {
        "name": "高潮",
        "function": "最终对决，决定胜负",
        "typical_elements": ["正面冲突", "能力/意志的终极考验", "胜负揭晓"],
        "pacing": "peak",
    },
    "falling_action": {
        "name": "下降动作",
        "function": "高潮后果展开",
        "typical_elements": ["收拾残局", "新秩序建立", "情感处理"],
        "pacing": "descending",
    },
    "resolution": {
        "name": "结局",
        "function": "矛盾解决，新常态确立",
        "typical_elements": ["最终画面", "主题回应", "余韵"],
        "pacing": "slow",
    },
}

# ============================================================
# 6. 叙事技法库 (Narrative Devices)
# ============================================================
NARRATIVE_DEVICE_LIBRARY: dict[str, dict] = {
    "foreshadowing": {
        "name": "伏笔/预兆",
        "description": "在早期暗示后续事件",
        "emotion_effect": "回味、满足感、命运感",
    },
    "flashback": {
        "name": "闪回",
        "description": "回到过去时间线",
        "emotion_effect": "揭示前因、对比、怀旧",
    },
    "flash_forward": {
        "name": "闪前",
        "description": "跳到未来时间线",
        "emotion_effect": "悬念、命运预感",
    },
    "unreliable_narrator": {
        "name": "不可靠叙述者",
        "description": "叙述者的信息/判断不可信",
        "emotion_effect": "怀疑、反转、真相揭示",
    },
    "red_herring": {
        "name": "红鲱鱼（误导）",
        "description": "故意误导观众的线索",
        "emotion_effect": "惊讶、恍然大悟",
    },
    "macguffin": {
        "name": "麦高芬",
        "description": "推动剧情但本身不重要的物件/目标",
        "emotion_effect": "驱动行动、转移注意力",
    },
    "deus_ex_machina": {
        "name": "机械降神",
        "description": "意外力量介入解决危机",
        "emotion_effect": "（通常负面）突兀、不满足",
    },
    "in_medias_res": {
        "name": "从中间开始",
        "description": "故事从中间切入，再回溯",
        "emotion_effect": "即时紧张、好奇心",
    },
    "frame_story": {
        "name": "框架叙事",
        "description": "故事中套故事",
        "emotion_effect": "层次感、多重视角",
    },
    "dramatic_irony": {
        "name": "戏剧反讽",
        "description": "观众知道角色不知道的信息",
        "emotion_effect": "紧张、焦虑、同情",
    },
    "parallel_storylines": {
        "name": "平行叙事",
        "description": "两条或多条时间线并行",
        "emotion_effect": "对比、呼应、命运交织",
    },
    "symbolism": {
        "name": "象征",
        "description": "用物件/意象代表抽象概念",
        "emotion_effect": "深层意义、诗意",
    },
}

# ============================================================
# 7. 节奏模板库 (Pacing Templates)
# ============================================================
PACING_TEMPLATE_LIBRARY: dict[str, dict] = {
    "slow_burn": {
        "name": "慢燃",
        "description": "缓慢铺垫，逐渐累积张力",
        "typical_duration": "长",
        "emotion_effect": "压抑、期待、最终爆发更强烈",
        "usage": "悬疑、心理剧、文艺片",
    },
    "roller_coaster": {
        "name": "过山车",
        "description": "高低起伏交替，节奏快速",
        "typical_duration": "中",
        "emotion_effect": "刺激、紧张、情绪波动",
        "usage": "动作片、商业大片",
    },
    "crescendo": {
        "name": "渐强",
        "description": "从平静逐渐加速到高潮",
        "typical_duration": "中-长",
        "emotion_effect": "紧张递增、最终释放",
        "usage": "战争片、灾难片、悲剧",
    },
    "frenetic": {
        "name": "狂乱",
        "description": "持续高强度，几乎没有喘息",
        "typical_duration": "短-中",
        "emotion_effect": "紧迫、焦虑、窒息感",
        "usage": "追逐戏、倒计时、恐怖片",
    },
    "contemplative": {
        "name": "沉思",
        "description": "大量留白，缓慢节奏",
        "typical_duration": "长",
        "emotion_effect": "内省、诗意、日常之美",
        "usage": "文艺片、慢电影、是枝裕和式",
    },
    "punch_line": {
        "name": "包袱节奏",
        "description": "快速setup + 延迟payoff",
        "typical_duration": "短",
        "emotion_effect": "幽默、意外、满足",
        "usage": "喜剧、情景喜剧",
    },
}


def get_character_archetype(archetype: str) -> dict:
    return CHARACTER_ARCHETYPE_LIBRARY.get(archetype, {})


def get_story_structure(structure: str) -> dict:
    return STORY_STRUCTURE_LIBRARY.get(structure, {})


def get_conflict_type(conflict: str) -> dict:
    return CONFLICT_TYPE_LIBRARY.get(conflict, {})


def get_dialogue_style(style: str) -> dict:
    return DIALOGUE_STYLE_LIBRARY.get(style, {})


def list_all_archetypes() -> list[str]:
    return list(CHARACTER_ARCHETYPE_LIBRARY.keys())


def list_all_structures() -> list[str]:
    return list(STORY_STRUCTURE_LIBRARY.keys())


def list_all_conflicts() -> list[str]:
    return list(CONFLICT_TYPE_LIBRARY.keys())


def list_all_dialogue_styles() -> list[str]:
    return list(DIALOGUE_STYLE_LIBRARY.keys())
