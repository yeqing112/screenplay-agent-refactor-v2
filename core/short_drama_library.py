"""AI Short Drama Libraries — AI 短剧/漫剧专属基础体系。

参考来源：
- 网易: 拆解100+部爆款短剧的单集万能节奏公式
- 提效录: AI短剧剧本指南 (hook密度/反转频次/情绪卡点)
- 云智博客: AI短剧最佳实践 (3秒留存/15秒认知变化/留存曲线)
- 550W AI: 2026爆款AI短剧剧本创作攻略
- 红果短剧官方教程: 期待/悬念/钩子设置底层逻辑
- Real Reel: Vertical Drama Beat Engine (Hook/Friction/Spike/Button)
- Buffer: Vertical Video Story Beats
- Filmustage: How to Write a Vertical Drama Script
- Screenburn: Microdrama Structure Guide
- Morphic: How to Create High-Quality Microdramas
- CapCut: Short-Form Video Storytelling for 60-Second Arc
- Created.cloud: Scale Microdramas with Beats & Templates

核心思想：AI 短剧不是电影的压缩版，而是独立的叙事媒介，有自己专属的结构语法。
"""

# ============================================================
# 1. 单集节奏引擎 (Episode Beat Engine)
# ============================================================
# 中国短剧行业称之为"节奏引擎"，ReelShort/DramaBox 实战验证
EPISODE_BEAT_ENGINE: dict[str, dict] = {
    "hook": {
        "name": "钩子",
        "time_range": "0-3秒",
        "function": "停止滑动，制造疑问/冲击",
        "rules": [
            "前3秒决定生死，不存在慢开场",
            "必须出现异常事件，不解释背景",
            "主角必须在画面中做出反应",
            "观众看完后必须产生一个明确疑问",
            "可以直接用全剧最炸的镜头作为钩子",
        ],
        "types": {
            "direct_conflict": "直接冲突型：当众打脸、背叛、对峙、离婚协议甩脸",
            "strong_suspense": "强悬念型：枪口对准主角、掉落DNA化验单、神秘来电",
            "extreme_contrast": "极致反差型：上一秒万众瞩目，下一秒跌落谷底",
            "shocking_reveal": "震撼揭示型：身份曝光、秘密被发现、真相大白",
            "time_pressure": "时间压力型：倒计时、即将爆炸、最后期限",
        },
        "emotion_intensity": 7,
        "common_mistakes": ["纯铺垫开场", "环境描写开场", "角色日常开场", "解释性旁白开场"],
    },
    "setup": {
        "name": "建立",
        "time_range": "3-15秒",
        "function": "快速交代核心矛盾、人物关系、主角目标",
        "rules": [
            "10秒之内必须交代清楚三件事：核心矛盾、人物关系、主角目标",
            "不需要解释矛盾背后的前因后果",
            "观众只需要知道「现在发生了什么」",
            "用一句话台词或一个动作完成建立",
        ],
        "emotion_intensity": 5,
    },
    "friction": {
        "name": "摩擦/升级",
        "time_range": "15-60秒",
        "function": "推进主线、加深矛盾、累积情绪",
        "rules": [
            "每20-30秒必须设置一处情绪节点",
            "台词要短、碎、锋利，杜绝大段长篇对话",
            "压抑-爆发交替，情绪来回起伏",
            "可以穿插一小段温情缓冲，但必须服务主线",
            "中段高密度推进，一句多余废话都不能留",
        ],
        "emotion_intensity": "4-9（波动）",
        "pacing_sub_beats": [
            {"time": "15-30秒", "name": "第一摩擦", "function": "抛出核心冲突，给第一次情绪释放"},
            {"time": "30-45秒", "name": "加码", "function": "冲突升级，赌注提高"},
            {"time": "45-55秒", "name": "蓄势", "function": "为高潮积蓄能量"},
        ],
    },
    "spike": {
        "name": "尖峰/高潮",
        "time_range": "55-80秒（或倒数10-15秒）",
        "function": "本集最大的单一冲击——证据转移、视角翻转、代价支付",
        "rules": [
            "必须是本集最炸的一刻",
            "静音后如果spike消失，说明它不是spike而是音量",
            "必须改变观众对之前事件的理解",
            "要出乎意料但情理之中",
        ],
        "emotion_intensity": 10,
    },
    "button": {
        "name": "按钮/悬念结尾",
        "time_range": "最后5-10秒",
        "function": "在问题处切断，不在答案处切断",
        "rules": [
            "卡在情绪最高点直接戛然而止，黑屏收尾",
            "钩子力度必须大于本集所有冲突",
            "比你觉得安全的时刻早2秒切断",
            "不要过度解释悬念，观众会感受到的",
            "制造「未完成感」——让观众心里悬着一口气",
        ],
        "types": {
            "suspense_hook": "悬念钩：抛出身份疑问、隐藏秘密，黑屏留白",
            "crisis_hook": "危机钩：尖刀落下、大门被暴力撞开、倒计时爆炸",
            "reversal_hook": "反转钩：一句颠覆前面所有剧情的台词，话音刚落直接切黑",
            "emotional_hook": "情感钩：告白/分手/误会的关键瞬间被打断",
            "visual_hook": "视觉钩：监控画面里一闪而过的熟悉面孔、意外出现的身影",
        },
        "emotion_intensity": 8,
    },
}

# ============================================================
# 2. 单集情绪节点模板 (Emotion Node Template)
# ============================================================
# 来自实战验证：按此节奏表写的剧本完播率高45%
EPISODE_EMOTION_NODES: list[dict] = [
    {"node": "开场钩子", "time": "0-3s", "emotion_value": 7, "purpose": "抓住注意力"},
    {"node": "困境建立", "time": "3-10s", "emotion_value": 4, "purpose": "让观众理解处境"},
    {"node": "冲突升级", "time": "10-25s", "emotion_value": 8, "purpose": "压力递增"},
    {"node": "小高潮", "time": "25-40s", "emotion_value": 9, "purpose": "第一次情绪释放"},
    {"node": "短暂缓解", "time": "40-50s", "emotion_value": 5, "purpose": "喘息，为更大爆发蓄力"},
    {"node": "反转", "time": "50-60s", "emotion_value": 3, "purpose": "颠覆预期，制造冲击"},
    {"node": "大高潮", "time": "60-75s", "emotion_value": 10, "purpose": "本集最炸时刻"},
    {"node": "悬念结尾", "time": "最后5-10s", "emotion_value": 6, "purpose": "驱动下一集点击"},
]

# ============================================================
# 3. 钩子类型库 (Hook Library)
# ============================================================
HOOK_LIBRARY: dict[str, dict] = {
    "opening_hook": {
        "name": "开场钩子",
        "purpose": "3秒内停止滑动",
        "pattern": "异常事件 + 明确角色 + 即时后果",
        "types": [
            "当众打脸/羞辱",
            "背叛/出轨现场",
            "激烈争吵/对峙",
            "神秘来电/信息",
            "身份突然曝光",
            "生死危机",
            "极端反差（从巅峰到谷底）",
            "震撼画面（血迹/破碎/倒地）",
        ],
        "forbidden": ["环境描写开场", "角色日常开场", "解释性旁白", "慢节奏铺垫"],
    },
    "cliffhanger_hook": {
        "name": "结尾悬念钩子",
        "purpose": "驱动下一集点击",
        "pattern": "在情绪最高点戛然而止",
        "types": [
            "悬念钩：身份疑问/隐藏秘密，黑屏留白",
            "危机钩：迫在眉睫的危险，倒计时",
            "反转钩：一句颠覆所有剧情的台词",
            "情感钩：告白/分手的关键瞬间被打断",
            "信息钩：监控画面/证据出现",
        ],
        "golden_rule": "把高潮「切开」，一半留到下一集",
    },
    "mid_hook": {
        "name": "中段钩子",
        "purpose": "每15秒维持注意力",
        "pattern": "每15秒一次认知变化",
        "types": [
            "新证据出现，改变观众判断",
            "角色做出选择，付出代价",
            "隐藏信息曝光",
            "关系突然变化",
            "小反转（身份/误会/证据）",
        ],
    },
    "series_hook": {
        "name": "系列钩子",
        "purpose": "驱动追完整部剧",
        "pattern": "大期待 + 小期待阶梯",
        "types": [
            "核心悬念：主角的终极目标能否实现",
            "身份悬念：主角的真实身份何时揭露",
            "关系悬念：CP能否走到一起",
            "命运悬念：主角能否逃过危机",
        ],
    },
}

# ============================================================
# 4. 短剧专属冲突库 (Short Drama Conflict Patterns)
# ============================================================
# 短剧冲突必须是结构性的——内置在前提中，而非场景中临时制造
SHORT_DRAMA_CONFLICT_PATTERNS: dict[str, dict] = {
    "identity_inversion": {
        "name": "身份反转",
        "pattern": "表面身份 vs 真实身份的巨大落差",
        "examples": ["保洁阿姨实际是隐退商界女王", "外卖小哥是隐藏富二代", "傻白甜是高智商黑客"],
        "hook_power": 10,
        "usage": "短剧最核心的爆款公式",
    },
    "public_humiliation_reversal": {
        "name": "当众羞辱→打脸反击",
        "pattern": "主角被当众羞辱→亮出证据→反转打脸",
        "examples": ["离婚宴上被撕孕检单→放出出轨视频", "被嘲笑穷→亮出黑卡", "被赶出家门→身份曝光"],
        "hook_power": 9,
        "usage": "情绪爽点，完播率保障",
    },
    "revenge_rebirth": {
        "name": "重生复仇",
        "pattern": "回到过去，带着前世记忆复仇",
        "examples": ["重生回到被害前一天", "穿越回离婚前", "回到被背叛的那天"],
        "hook_power": 10,
        "usage": "长线叙事核心驱动力",
    },
    "forced_proximity": {
        "name": "被迫亲密",
        "pattern": "不应该靠近的两个人被困在一起",
        "examples": ["契约婚姻", "同一屋檐下", "被锁在同一空间"],
        "hook_power": 7,
        "usage": "甜宠/情感线核心",
    },
    "power_imbalance": {
        "name": "权力不对等",
        "pattern": "地位/资源/信息的极端不对等",
        "examples": ["霸道总裁vs小白领", "豪门婆婆vs灰姑娘媳妇", "上司vs下属"],
        "hook_power": 8,
        "usage": "制造天然冲突和压迫感",
    },
    "secret_revelation": {
        "name": "秘密揭露",
        "pattern": "隐藏的秘密逐步被发现",
        "examples": ["孩子不是亲生的", "当年的真相", "隐藏的婚史"],
        "hook_power": 9,
        "usage": "悬念驱动，每集揭露一层",
    },
    "ticking_clock": {
        "name": "倒计时",
        "pattern": "有限时间内必须完成某事",
        "examples": ["24小时内凑齐钱", "婚礼前夜发现真相", "最后3天生命"],
        "hook_power": 8,
        "usage": "制造紧迫感",
    },
    "love_triangle": {
        "name": "三角关系",
        "pattern": "三个人的情感纠葛",
        "examples": ["闺蜜抢男友", "前任vs现任", "兄弟争一人"],
        "hook_power": 7,
        "usage": "情感冲突核心",
    },
}

# ============================================================
# 5. 短剧专属对白库 (Short Drama Dialogue)
# ============================================================
# 短剧对白铁律：每一句要么推进冲突，要么揭示角色，否则删掉
SHORT_DRAMA_DIALOGUE_RULES: dict[str, dict] = {
    "golden_rules": [
        "台词要短、碎、锋利，杜绝大段长篇对话",
        "每一句要么推进冲突，要么揭示角色，否则删掉",
        "台词是动作——不是解释，不是抒情，是推进",
        "潜台词比明台词更有力",
        "用最少的词传递最大的信息量",
    ],
    "line_types": {
        "conflict_line": "冲突台词：制造/升级矛盾（你真以为我不知道你是谁？）",
        "revelation_line": "揭示台词：释放关键信息（明天股东大会，我会让你一无所有）",
        "emotional_line": "情绪台词：表达强烈情感（我这辈子最后悔的事，就是认识你）",
        "cliff_line": "悬念台词：留下疑问（你知道那天晚上真正发生了什么吗……）",
        "counter_line": "反击台词：被打脸后的反击（你以为这样就完了？）",
        "silence": "沉默：比任何台词都重的停顿",
    },
    "forbidden_patterns": [
        "大段解释性旁白",
        "角色独白超过2句",
        "环境描写式台词",
        "过于文艺/书面化的表达",
        "重复已知信息",
    ],
}

# ============================================================
# 6. 短剧视觉语法库 (Short Drama Visual Grammar)
# ============================================================
SHORT_DRAMA_VISUAL_GRAMMAR: dict[str, dict] = {
    "framing": {
        "name": "竖屏构图",
        "rules": [
            "特写/近景为主，面部和眼睛是核心",
            "人物居中，留好上下空间",
            "避免头顶或脚被裁掉",
            "两个角色对话用正反打，不用双人横构图",
            "竖屏中垂直运动（上下）比横向运动更有效",
        ],
    },
    "shot_duration": {
        "name": "镜头时长",
        "rules": [
            "单镜头3-8秒，适合AI视频生成",
            "每个镜头只有一个主要动作",
            "高潮处用更快的剪辑节奏",
            "安静处可以稍长，但不超过6秒",
        ],
    },
    "expression_priority": {
        "name": "表情优先",
        "rules": [
            "竖屏短剧靠脸吃饭，不是靠场景",
            "情绪微表情比任何对白都重要",
            "特写镜头要给够时间让观众读表情",
            "反应镜头（reaction shot）是最重要的镜头之一",
        ],
    },
    "ai_consistency": {
        "name": "AI一致性",
        "rules": [
            "主角用2-3个锚点属性（标志性服装/发型/配饰）",
            "每条提示词逐字重复人物一致句",
            "场景不超过20秒切换一次",
            "主光方向在同一场景内必须一致",
            "台词下方必须叠环境声铺底",
        ],
    },
}

# ============================================================
# 7. 短剧节奏模板库 (Short Drama Pacing Templates)
# ============================================================
SHORT_DRAMA_PACING_TEMPLATES: dict[str, dict] = {
    "60s_speed": {
        "name": "60秒极速",
        "total_duration": "60秒",
        "structure": "钩子(3s) + 建立(7s) + 冲突(20s) + 高潮(20s) + 悬念(10s)",
        "beats": 5,
        "hook_to_conflict": "10秒内",
        "反转次数": "1-2次",
        "usage": "小程序剧、极短篇",
    },
    "90s_standard": {
        "name": "90秒标准",
        "total_duration": "90秒",
        "structure": "钩子(3s) + 建立(12s) + 摩擦(30s) + 尖峰(25s) + 悬念(10s)",
        "beats": 5,
        "hook_to_conflict": "15秒内",
        "反转次数": "2-3次",
        "usage": "主流竖屏短剧",
    },
    "120s_extended": {
        "name": "120秒完整",
        "total_duration": "120秒",
        "structure": "钩子(3s) + 建立(12s) + 摩擦(45s) + 尖峰(35s) + 悬念(10s)",
        "beats": 6,
        "hook_to_conflict": "15秒内",
        "反转次数": "3-4次",
        "usage": "完整剧情集、红果版",
    },
    "180s_deep": {
        "name": "180秒深度",
        "total_duration": "180秒",
        "structure": "钩子(3s) + 建立(15s) + 摩擦(80s) + 尖峰(55s) + 悬念(10s)",
        "beats": 7,
        "hook_to_conflict": "15秒内",
        "反转次数": "4-5次",
        "usage": "深度剧情、人物弧完整",
    },
}

# ============================================================
# 8. 短剧系列架构库 (Series Architecture)
# ============================================================
SERIES_ARCHITECTURE_LIBRARY: dict[str, dict] = {
    "episode_1_3": {
        "name": "开篇1-3集",
        "function": "极速铺世界观、立牢主角人设、抛出主线大矛盾",
        "rules": [
            "第1集：强冲突开场+核心悬念建立",
            "第2集：主角尝试解决，发现更大阻力",
            "第3集：安排一次小爆点，留住第一批观众",
        ],
    },
    "episode_mid": {
        "name": "剧集中段",
        "function": "三集一次小反转爽点，五集一次大型高潮",
        "rules": [
            "爽点和虐点交替穿插，避免审美疲劳",
            "每10集安排一次大高潮",
            "第8-10集：超级钩子（引导付费）",
            "身份揭秘/打脸高能放在付费卡点",
        ],
    },
    "episode_finale": {
        "name": "临近大结局",
        "function": "叠加连环反转，放出终极冲突",
        "rules": [
            "叠加连环反转",
            "放出终极冲突",
            "把全剧情绪推到顶峰",
            "完整结局+彩蛋伏笔",
            "预留续集钩子",
        ],
    },
    "tentpole_episodes": {
        "name": "支点集",
        "function": "关键转折集，重新定价整个故事",
        "rules": [
            "E5：重新定价前提（新规则让观众理解全错）",
            "E10：碰撞全剧两个最大秘密",
            "不要把最好的beat留到第8集——前2-3集就要值",
        ],
    },
    "series_length": {
        "name": "集数规划",
        "sweet_spot": "60-100集",
        "per_episode": "60-120秒",
        "total_runtime": "90-150分钟（≈一部电影）",
        "arc_count": "3-5个大弧线，每个15-25集",
    },
}

# ============================================================
# 9. 短剧致命坑库 (Common Pitfalls)
# ============================================================
COMMON_PITFALLS: dict[str, dict] = {
    "slow_opening": {
        "name": "开场铺垫超过10秒",
        "consequence": "观众直接划走，前期流量全部浪费",
        "fix": "开篇直接上高潮，不存在慢开场",
    },
    "no_cliffhanger": {
        "name": "结尾没有钩子",
        "consequence": "冲突平缓收尾，没有追更欲望",
        "fix": "卡在情绪最高点戛然而止",
    },
    "endless_suffering": {
        "name": "长时间持续虐主角",
        "consequence": "观众看得压抑，直接弃剧",
        "fix": "虐-爽交替，每20-30秒一个情绪释放",
    },
    "too_much_dialogue": {
        "name": "大段长篇对话",
        "consequence": "节奏拖沓，AI生成口型对不上",
        "fix": "台词短碎锋利，每段1-2句",
    },
    "exposition_dump": {
        "name": "解释性旁白/设定堆砌",
        "consequence": "观众3秒划走",
        "fix": "用动作和画面传递信息，不解释",
    },
    "ai_detection": {
        "name": "纯AI一键生成",
        "consequence": "被平台AI检测拒稿",
        "fix": "人工润色20-30%，增加原创度",
    },
    "cold_topic": {
        "name": "碰冷门题材",
        "consequence": "AI训练数据少，爆款率低",
        "fix": "新人首选重生复仇/豪门虐恋/逆袭打脸",
    },
    "pacing_dilution": {
        "name": "节奏拖沓（AI通病）",
        "consequence": "一个对视写200字，观众流失",
        "fix": "人工砍戏，把每集节奏压到极致",
    },
}


# ============================================================
# 10. 短剧情绪卡点库 (Emotion Checkpoint Library)
# ============================================================
# 每集选1-2个情绪主基调，纯度越高越容易爆
EMOTION_CHECKPOINT_LIBRARY: dict[str, dict] = {
    "abuse": {
        "name": "虐",
        "emotion_code": "虐",
        "triggers": ["被冤枉", "被抛弃", "被背叛", "被羞辱", "误解"],
        "intensity": "压抑→爆发",
        "usage": "制造情绪低谷，为爽点蓄力",
    },
    "satisfy": {
        "name": "爽",
        "emotion_code": "爽",
        "triggers": ["打脸", "复仇", "逆袭", "身份曝光", "真相大白"],
        "intensity": "释放→满足",
        "usage": "情绪高点，完播率保障",
    },
    "sweet": {
        "name": "甜",
        "emotion_code": "甜",
        "triggers": ["亲吻", "告白", "求婚", "守护", "误会解除"],
        "intensity": "温暖→心动",
        "usage": "CP线情感驱动",
    },
    "燃": {
        "name": "燃",
        "emotion_code": "燃",
        "triggers": ["对抗强敌", "逆风翻盘", "宣言", "牺牲", "觉醒"],
        "intensity": "压抑→爆发→升华",
        "usage": "高潮时刻，情绪顶峰",
    },
    "suspense": {
        "name": "悬",
        "emotion_code": "悬",
        "triggers": ["秘密揭露", "身份疑问", "危机逼近", "倒计时"],
        "intensity": "好奇→紧张→焦虑",
        "usage": "悬念驱动，追更动力",
    },
}


def get_beat_engine(beat: str) -> dict:
    return EPISODE_BEAT_ENGINE.get(beat, {})


def get_hook(hook_type: str, hook_category: str = "opening_hook") -> dict:
    return HOOK_LIBRARY.get(hook_category, {}).get("types", {}).get(hook_type, {})


def get_pacing_template(duration: str) -> dict:
    return SHORT_DRAMA_PACING_TEMPLATES.get(duration, {})


def list_all_hook_types() -> list[str]:
    all_hooks = []
    for category in HOOK_LIBRARY.values():
        all_hooks.extend(category.get("types", []))
    return all_hooks
