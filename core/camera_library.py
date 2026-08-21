"""Camera Library — 标准化镜头运动术语映射。

参考来源：
- AI 影视生产系统 V1.0 第 7 节
- NFI Camera Movement Terms (17 types)
- ZOOOP 运镜方式百科
- StudioBinder Camera Movements Guide
- Columbia Film Language Glossary
- Morphic AI Camera Motion Glossary

核心思想：摄影术语不应每次由 LLM 即兴生成，应使用标准化映射。
"""

CAMERA_LIBRARY: dict[str, dict] = {
    # === 静态 ===
    "static": {
        "code": "CAM001",
        "zh": "镜头固定不动",
        "en": "The camera remains static.",
        "category": "static",
        "speed_variants": {},
        "stability": "steady",
        "emotion_effect": "稳定、客观、等待、压抑",
        "usage": "对话场景默认、情绪麻木、仪式感停留",
    },
    "locked_off": {
        "code": "CAM002",
        "zh": "完全锁定，禁止任何漂移",
        "en": "The camera is locked off on a tripod, no movement whatsoever.",
        "category": "static",
        "speed_variants": {},
        "stability": "locked",
        "emotion_effect": "绝对静止、旁观、时间冻结",
        "usage": "需要完全不动的镜头，对抗模型默认漂移",
    },

    # === 纵向推拉（dolly）===
    "push_in": {
        "code": "CAM010",
        "zh": "镜头沿轨道向主体推进",
        "en": "The camera dollies in toward the subject.",
        "category": "dolly",
        "speed_variants": {
            "very_slow": "极缓慢推进，几乎察觉不到，持续加压",
            "slow": "缓慢推进，营造积蓄感",
            "medium": "中速推进，节奏感明确",
            "fast": "快速推进，冲击力强",
        },
        "stability": "steady",
        "emotion_effect": "聚焦、紧张递进、心理冲击、情感升温",
        "usage": "情绪递进、心理揭示、强调重要性",
    },
    "pull_out": {
        "code": "CAM011",
        "zh": "镜头沿轨道远离主体",
        "en": "The camera dollies out from the subject.",
        "category": "dolly",
        "speed_variants": {
            "slow": "缓慢拉远，揭示全貌",
            "medium": "中速拉远，节奏转换",
        },
        "stability": "steady",
        "emotion_effect": "疏离、揭示、孤独感、全局视角",
        "usage": "场景建立、人物孤立、情绪冷却",
    },
    "dolly_zoom": {
        "code": "CAM012",
        "zh": "推轨与变焦反向同时进行，主体大小不变而背景形变",
        "en": "Dolly zoom: camera dollies in while zooming out (or vice versa), subject stays same size but background distorts.",
        "category": "dolly",
        "speed_variants": {
            "slow": "缓慢推轨变焦，眩晕感渐强",
        },
        "stability": "steady",
        "emotion_effect": "眩晕、不安、心理失衡、时空扭曲",
        "usage": "惊悚/悬疑片经典技法，希区柯克式",
    },

    # === 横向移动（truck/track）===
    "truck_left": {
        "code": "CAM020",
        "zh": "镜头向左横向移动",
        "en": "The camera trucks left.",
        "category": "truck",
        "speed_variants": {
            "slow": "缓慢左移，平行叙事",
            "medium": "中速左移，跟踪移动",
        },
        "stability": "steady",
        "emotion_effect": "平行跟随、空间展示",
        "usage": "与运动主体平行移动",
    },
    "truck_right": {
        "code": "CAM021",
        "zh": "镜头向右横向移动",
        "en": "The camera trucks right.",
        "category": "truck",
        "speed_variants": {
            "slow": "缓慢右移，平行叙事",
            "medium": "中速右移，跟踪移动",
        },
        "stability": "steady",
        "emotion_effect": "平行跟随、空间展示",
        "usage": "与运动主体平行移动",
    },
    "tracking": {
        "code": "CAM022",
        "zh": "镜头跟随主体持续移动",
        "en": "The camera tracks alongside the subject.",
        "category": "truck",
        "speed_variants": {
            "slow": "缓慢跟拍，沉浸感",
            "medium": "中速跟拍，节奏感",
            "fast": "快速跟拍，紧迫感",
        },
        "stability": "steady",
        "emotion_effect": "跟随、沉浸、平行叙事、紧迫",
        "usage": "角色行走/奔跑跟拍，对话中的平行移动",
    },
    "follow": {
        "code": "CAM023",
        "zh": "镜头跟随主体运动，保持相对距离",
        "en": "The camera follows the subject at a consistent distance.",
        "category": "truck",
        "speed_variants": {
            "slow": "缓慢跟随",
            "medium": "中速跟随",
        },
        "stability": "steady",
        "emotion_effect": "代入感、主观视角、陪伴感",
        "usage": "展示主体视角，观众跟随角色",
    },

    # === 摇摄（pan/tilt）===
    "pan_left": {
        "code": "CAM030",
        "zh": "镜头向左水平摇摄",
        "en": "The camera pans left.",
        "category": "pan",
        "speed_variants": {
            "slow": "缓慢左摇，展示空间",
            "medium": "中速左摇，跟踪移动",
            "fast": "快速甩摇（whip pan），模糊过渡",
        },
        "stability": "steady",
        "emotion_effect": "空间展示、视线引导、场景交代",
        "usage": "环顾环境、引导视线、转场",
    },
    "pan_right": {
        "code": "CAM031",
        "zh": "镜头向右水平摇摄",
        "en": "The camera pans right.",
        "category": "pan",
        "speed_variants": {
            "slow": "缓慢右摇，展示空间",
            "medium": "中速右摇，跟踪移动",
            "fast": "快速甩摇（whip pan），模糊过渡",
        },
        "stability": "steady",
        "emotion_effect": "空间展示、视线引导、场景交代",
        "usage": "环顾环境、引导视线、转场",
    },
    "whip_pan": {
        "code": "CAM032",
        "zh": "快速甩摇，画面拖出运动模糊",
        "en": "Whip pan: extremely fast pan that creates motion blur, used as transition.",
        "category": "pan",
        "speed_variants": {},
        "stability": "blur",
        "emotion_effect": "能量爆发、快速转场、紧张节奏",
        "usage": "转场过渡、动作场景节奏加速",
    },
    "tilt_up": {
        "code": "CAM033",
        "zh": "镜头向上垂直摇摄",
        "en": "The camera tilts up.",
        "category": "tilt",
        "speed_variants": {
            "slow": "缓慢上摇，揭示高度",
            "medium": "中速上摇，建立规模感",
        },
        "stability": "steady",
        "emotion_effect": "仰望、敬畏、揭示全貌、建立权威",
        "usage": "展示建筑高度、人物登场、揭示上方信息",
    },
    "tilt_down": {
        "code": "CAM034",
        "zh": "镜头向下垂直摇摄",
        "en": "The camera tilts down.",
        "category": "tilt",
        "speed_variants": {
            "slow": "缓慢下摇，聚焦细节",
            "medium": "中速下摇",
        },
        "stability": "steady",
        "emotion_effect": "俯视、压迫感、聚焦低处、揭示下方",
        "usage": "从全景到局部、展示地面细节、压迫感",
    },

    # === 环绕（arc/orbit）===
    "orbit_left": {
        "code": "CAM040",
        "zh": "镜头沿弧线环绕主体向左旋转",
        "en": "The camera arcs left around the subject.",
        "category": "arc",
        "speed_variants": {
            "slow": "缓慢环绕，营造仪式感",
            "medium": "中速环绕，动态感",
        },
        "stability": "steady",
        "emotion_effect": "仪式感、全视角展示、时间停滞、戏剧性",
        "usage": "重要时刻、角色揭示、情感高潮",
    },
    "orbit_right": {
        "code": "CAM041",
        "zh": "镜头沿弧线环绕主体向右旋转",
        "en": "The camera arcs right around the subject.",
        "category": "arc",
        "speed_variants": {
            "slow": "缓慢环绕，营造仪式感",
        },
        "stability": "steady",
        "emotion_effect": "仪式感、全视角展示、时间停滞",
        "usage": "重要时刻、角色揭示、情感高潮",
    },

    # === 升降（crane/boom/jib）===
    "crane_up": {
        "code": "CAM050",
        "zh": "摇臂升起，镜头向上移动",
        "en": "The camera cranes up.",
        "category": "crane",
        "speed_variants": {
            "slow": "缓慢升起，揭示全貌",
            "medium": "中速升起，规模感",
        },
        "stability": "steady",
        "emotion_effect": "揭示、升华、全局视角、史诗感",
        "usage": "场景建立、结局升华、从局部到全局",
    },
    "crane_down": {
        "code": "CAM051",
        "zh": "摇臂下降，镜头向下移动",
        "en": "The camera cranes down.",
        "category": "crane",
        "speed_variants": {
            "slow": "缓慢下降，聚焦",
            "medium": "中速下降",
        },
        "stability": "steady",
        "emotion_effect": "聚焦、进入场景、亲密感",
        "usage": "从全局到局部、进入室内、建立亲密",
    },
    "boom": {
        "code": "CAM052",
        "zh": "垂直升降镜头",
        "en": "The camera booms up/down vertically.",
        "category": "crane",
        "speed_variants": {
            "slow": "缓慢升降",
        },
        "stability": "steady",
        "emotion_effect": "规模感、空间转换",
        "usage": "建立镜头、展示场景纵深",
    },
    "pedestal": {
        "code": "CAM053",
        "zh": "基座垂直升降",
        "en": "The camera pedestals up or down.",
        "category": "crane",
        "speed_variants": {
            "slow": "缓慢升降",
        },
        "stability": "steady",
        "emotion_effect": "视角垂直变化、揭示",
        "usage": "展示高度变化、从低到高",
    },

    # === 变焦（zoom）===
    "zoom_in": {
        "code": "CAM060",
        "zh": "变焦推近，焦距变化放大画面",
        "en": "The camera zooms in (changes focal length).",
        "category": "zoom",
        "speed_variants": {
            "slow": "缓慢变焦推近",
            "medium": "中速变焦推近",
            "fast": "快速变焦推近（希区柯克式）",
        },
        "stability": "steady",
        "emotion_effect": "紧张递进、心理压迫、焦点锁定、旁观感",
        "usage": "注意：变焦=旁观，推轨=置身其中",
    },
    "zoom_out": {
        "code": "CAM061",
        "zh": "变焦拉远，焦距变化缩小画面",
        "en": "The camera zooms out (changes focal length).",
        "category": "zoom",
        "speed_variants": {
            "slow": "缓慢变焦拉远",
            "medium": "中速变焦拉远",
        },
        "stability": "steady",
        "emotion_effect": "揭示全局、疏离感、观察视角",
        "usage": "揭示环境、创造距离感",
    },

    # === 手持/稳定器 ===
    "handheld": {
        "code": "CAM070",
        "zh": "手持拍摄，带有可见的轻微晃动",
        "en": "The camera is handheld with visible shake.",
        "category": "stabilization",
        "speed_variants": {
            "gentle": "轻微手持晃动，自然感",
            "heavy": "剧烈手持晃动，混乱感",
        },
        "stability": "slight_shake",
        "emotion_effect": "紧张、真实感、不安、纪录片质感、混乱",
        "usage": "混乱场景、追逐、亲密时刻、纪录片风格",
    },
    "steadicam": {
        "code": "CAM071",
        "zh": "斯坦尼康稳定跟拍，流畅无抖动",
        "en": "Steadicam: smooth, fluid camera movement without shake.",
        "category": "stabilization",
        "speed_variants": {
            "slow": "缓慢稳定跟拍",
            "medium": "中速稳定跟拍",
            "fast": "快速稳定跟拍",
        },
        "stability": "smooth",
        "emotion_effect": "流畅、沉浸、梦幻、优雅",
        "usage": "长镜头、复杂空间穿行、舞蹈场景",
    },

    # === 焦点操控 ===
    "rack_focus": {
        "code": "CAM080",
        "zh": "焦点从前景主体转移到背景（或反之）",
        "en": "Rack focus: shift focus from one subject to another in a continuous shot.",
        "category": "focus",
        "speed_variants": {
            "slow": "缓慢焦点转移，渐变",
            "fast": "快速焦点切换",
        },
        "stability": "steady",
        "emotion_effect": "注意力转移、信息揭示、心理暗示",
        "usage": "对话中的反应镜头、揭示隐藏信息",
    },

    # === 旋转 ===
    "roll": {
        "code": "CAM090",
        "zh": "镜头绕光轴旋转",
        "en": "The camera rolls along its optical axis.",
        "category": "roll",
        "speed_variants": {
            "slow": "缓慢旋转，眩晕感",
            "half": "旋转半圈停住（荷兰角变体）",
        },
        "stability": "rotating",
        "emotion_effect": "眩晕、混乱、心理失衡、梦境",
        "usage": "醉酒/受伤主观镜头、心理崩溃、梦境",
    },

    # === 综合运动 ===
    "compound": {
        "code": "CAM100",
        "zh": "复合运动（多轴向组合）",
        "en": "Compound movement combining multiple axes.",
        "category": "compound",
        "speed_variants": {},
        "stability": "varies",
        "emotion_effect": "取决于组合方式",
        "usage": "复杂场景的多段运动，建议分段用首尾帧衔接",
    },
}

# === 景别标准术语 ===
SHOT_SIZE_LIBRARY: dict[str, dict[str, str]] = {
    "ELS": {
        "zh": "大远景",
        "en": "Extreme Long Shot",
        "usage": "展示宏大场景、环境全貌、人物渺小",
        "body_range": "人物占画面极小比例",
    },
    "LS": {
        "zh": "远景",
        "en": "Long Shot",
        "usage": "展示场景与人物全身关系",
        "body_range": "人物全身，约占画面高度",
    },
    "MLS": {
        "zh": "中全景",
        "en": "Medium Long Shot",
        "usage": "展示人物全身与环境关系",
        "body_range": "人物膝盖以上",
    },
    "MS": {
        "zh": "中景",
        "en": "Medium Shot",
        "usage": "人物对话、日常动作",
        "body_range": "人物腰部以上",
    },
    "MCU": {
        "zh": "中近景",
        "en": "Medium Close-up",
        "usage": "人物上半身、表情与手势",
        "body_range": "人物胸部以上",
    },
    "CU": {
        "zh": "特写",
        "en": "Close-up",
        "usage": "表情变化、关键道具、情绪爆发点",
        "body_range": "人物肩部以上或局部",
    },
    "ECU": {
        "zh": "极特写",
        "en": "Extreme Close-up",
        "usage": "眼睛、嘴唇、手指微动等极致细节",
        "body_range": "面部局部或更小",
    },
    "OTS": {
        "zh": "过肩镜头",
        "en": "Over-the-shoulder Shot",
        "usage": "对话场景、建立空间关系",
        "body_range": "前景人物肩部+后景人物",
    },
    "POV": {
        "zh": "主观镜头",
        "en": "Point-of-view Shot",
        "usage": "角色视角、增强代入感",
        "body_range": "角色所见画面",
    },
    "insert": {
        "zh": "插入镜头",
        "en": "Insert Shot",
        "usage": "特写道具/细节，补充信息",
        "body_range": "局部特写",
    },
    "OTS_CU": {
        "zh": "过肩特写",
        "en": "Over-the-shoulder Close-up",
        "usage": "对话中强调一方反应",
        "body_range": "前景肩部虚化+后景人物特写",
    },
}

# === 机位角度术语 ===
CAMERA_ANGLE_LIBRARY: dict[str, dict[str, str]] = {
    "eye_level": {
        "zh": "平视",
        "en": "Eye-level angle",
        "usage": "自然视角、人物对话默认、平等关系",
    },
    "low_angle": {
        "zh": "仰拍",
        "en": "Low angle",
        "usage": "人物高大、威严、压迫感、英雄感",
    },
    "high_angle": {
        "zh": "俯拍",
        "en": "High angle",
        "usage": "人物渺小、脆弱、全局视角、审视",
    },
    "dutch_angle": {
        "zh": "倾斜构图（荷兰角）",
        "en": "Dutch angle / Canted angle",
        "usage": "不安、混乱、心理失衡、疯狂",
    },
    "birds_eye": {
        "zh": "鸟瞰",
        "en": "Bird's eye view",
        "usage": "上帝视角、场景全貌、上帝视角审视",
    },
    "worms_eye": {
        "zh": "蛙眼视角",
        "en": "Worm's eye view",
        "usage": "极端仰拍、压迫感、戏剧性",
    },
    "over_shoulder": {
        "zh": "过肩镜头",
        "en": "Over-the-shoulder shot",
        "usage": "对话场景、建立空间关系、主观视角",
    },
    "three_quarter": {
        "zh": "三分之四角度",
        "en": "Three-quarter angle",
        "usage": "人物肖像、展示面部轮廓",
    },
    "profile": {
        "zh": "侧面角度",
        "en": "Profile angle",
        "usage": "剪影效果、对峙、平行叙事",
    },
    "canted": {
        "zh": "倾斜构图",
        "en": "Canted angle",
        "usage": "与 Dutch angle 同义，不安感",
    },
}

# === 转场方式标准化 ===
TRANSITION_LIBRARY: dict[str, dict[str, str]] = {
    "cut": {
        "zh": "直切",
        "en": "Cut",
        "usage": "最常用转场，时间/空间瞬时切换",
    },
    "dissolve": {
        "zh": "叠化",
        "en": "Dissolve",
        "usage": "时间流逝、回忆、梦境过渡",
    },
    "fade_in": {
        "zh": "淡入",
        "en": "Fade in",
        "usage": "场景开始、新段落引入",
    },
    "fade_out": {
        "zh": "淡出",
        "en": "Fade out",
        "usage": "场景结束、情感收束",
    },
    "fade_to_black": {
        "zh": "淡出至黑",
        "en": "Fade to black",
        "usage": "段落终结、时间跳跃、情绪沉淀",
    },
    "wipe": {
        "zh": "划像",
        "en": "Wipe",
        "usage": "空间转换、场景切换",
    },
    "match_cut": {
        "zh": "匹配剪辑",
        "en": "Match cut",
        "usage": "相似形状/动作的视觉关联转场",
    },
    "jump_cut": {
        "zh": "跳切",
        "en": "Jump cut",
        "usage": "时间压缩、紧张节奏、打破连续性",
    },
    "smash_cut": {
        "zh": "猛切",
        "en": "Smash cut",
        "usage": "突然的情绪/场景转换，冲击力强",
    },
    "whip_pan_transition": {
        "zh": "甩摇转场",
        "en": "Whip pan transition",
        "usage": "快速甩摇模糊中完成转场",
    },
    "cross_dissolve": {
        "zh": "交叉溶解",
        "en": "Cross dissolve",
        "usage": "两个场景交替渐变",
    },
    "iris": {
        "zh": "光圈转场",
        "en": "Iris transition",
        "usage": "经典默片风格，圆形遮罩开合",
    },
}

# === 光影氛围标准化 ===
LIGHTING_LIBRARY: dict[str, dict[str, str]] = {
    "natural": {
        "zh": "自然光",
        "en": "Natural lighting",
        "usage": "户外场景、日常感、真实感",
    },
    "golden_hour": {
        "zh": "黄金时段光线",
        "en": "Golden hour lighting",
        "usage": "温暖、浪漫、怀旧、回忆",
    },
    "blue_hour": {
        "zh": "蓝色时刻光线",
        "en": "Blue hour lighting",
        "usage": "冷调、忧郁、黎明/黄昏",
    },
    "high_key": {
        "zh": "高调照明",
        "en": "High-key lighting",
        "usage": "明亮、轻快、喜剧、梦幻",
    },
    "low_key": {
        "zh": "低调照明",
        "en": "Low-key lighting",
        "usage": "明暗对比强、悬疑、黑色电影",
    },
    "chiaroscuro": {
        "zh": "明暗对比法",
        "en": "Chiaroscuro lighting",
        "usage": "极端明暗对比、戏剧性、伦勃朗光",
    },
    "rim_light": {
        "zh": "轮廓光",
        "en": "Rim lighting",
        "usage": "勾勒轮廓、神圣感、分离主体与背景",
    },
    "backlight": {
        "zh": "逆光",
        "en": "Backlighting",
        "usage": "剪影效果、神秘感、轮廓勾勒",
    },
    "side_light": {
        "zh": "侧光",
        "en": "Side lighting",
        "usage": "面部立体感、戏剧性、半明半暗",
    },
    "soft_diffused": {
        "zh": "柔和漫射光",
        "en": "Soft diffused lighting",
        "usage": "温柔、亲密、梦幻、回忆",
    },
    "hard_direct": {
        "zh": "硬直射光",
        "en": "Hard direct lighting",
        "usage": "强烈阴影、正午感、紧张",
    },
    "neon": {
        "zh": "霓虹灯光",
        "en": "Neon lighting",
        "usage": "都市感、夜生活、赛博朋克",
    },
    "fluorescent": {
        "zh": "荧光灯照明",
        "en": "Fluorescent lighting",
        "usage": "医院、办公室、冷漠感",
    },
    "candlelight": {
        "zh": "烛光",
        "en": "Candlelight",
        "usage": "温馨、亲密、复古、仪式感",
    },
    "moonlight": {
        "zh": "月光",
        "en": "Moonlight",
        "usage": "夜晚、孤独、浪漫、神秘",
    },
    "tungsten": {
        "zh": "钨丝灯暖光",
        "en": "Tungsten lighting",
        "usage": "室内暖调、怀旧、家庭感",
    },
    "mixed_color_temp": {
        "zh": "混合色温",
        "en": "Mixed color temperature lighting",
        "usage": "冷暖交错、心理冲突、不安",
    },
}


def get_camera_description(motion: str, speed: str = "slow") -> str:
    """返回标准化的镜头运动描述。"""
    entry = CAMERA_LIBRARY.get(motion, CAMERA_LIBRARY["static"])
    speed_variants = entry.get("speed_variants", {})
    if speed_variants:
        return speed_variants.get(speed, entry.get("zh", ""))
    return entry.get("zh", "镜头固定不动")


def get_camera_en(motion: str, speed: str = "slow") -> str:
    """返回英文镜头运动描述（用于多模型适配）"""
    entry = CAMERA_LIBRARY.get(motion, CAMERA_LIBRARY["static"])
    return entry.get("en", "The camera remains static.")


def get_shot_size_zh(shot_size: str) -> str:
    """返回景别的中文名称"""
    entry = SHOT_SIZE_LIBRARY.get(shot_size, SHOT_SIZE_LIBRARY["MS"])
    return entry.get("zh", "中景")


def get_camera_angle_zh(angle: str) -> str:
    """返回机位角度的中文名称"""
    entry = CAMERA_ANGLE_LIBRARY.get(angle, CAMERA_ANGLE_LIBRARY["eye_level"])
    return entry.get("zh", "平视")


def get_transition_zh(transition: str) -> str:
    """返回转场方式的中文名称"""
    entry = TRANSITION_LIBRARY.get(transition, TRANSITION_LIBRARY["cut"])
    return entry.get("zh", "直切")


def get_lighting_zh(lighting: str) -> str:
    """返回光影氛围的中文名称"""
    entry = LIGHTING_LIBRARY.get(lighting, LIGHTING_LIBRARY["natural"])
    return entry.get("zh", "自然光")


def list_all_camera_motions() -> list[str]:
    """返回所有可用的镜头运动 key"""
    return list(CAMERA_LIBRARY.keys())


def list_motions_by_category(category: str) -> list[str]:
    """按类别筛选镜头运动"""
    return [k for k, v in CAMERA_LIBRARY.items() if v.get("category") == category]
