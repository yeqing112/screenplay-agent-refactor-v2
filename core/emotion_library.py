"""Emotion Motion Library — 抽象情绪到可视动作的标准化映射。

参考来源：
- AI 影视生产系统 V1.0 第 7.1 节
- FACS (Facial Action Coding System) 面部动作编码系统
- 7 Universal Expressions (Ekman): anger, disgust, fear, happiness, sadness, surprise, contempt
- facial-expression-prompting Skill (GitHub zhouwei713)
- Speech Graphics SGX 情绪控制器
- Seedance 2.0 情绪 AI 文档
- Actor's Pulse 肢体语言指南

核心思想：抽象情绪必须编译为可观察的面部和身体动作，避免只输出"她很害怕"。
"""

EMOTION_MOTION_LIBRARY: dict[str, dict[str, str]] = {
    # === 消极情绪 ===
    "害怕": {
        "low": "眼睛略睁大、下眼睑轻微紧张",
        "medium": "嘴唇微张、呼吸变浅、身体僵硬",
        "high": "瞳孔放大、嘴唇颤抖、身体后缩、双手不自觉握紧",
        "facs_au": "AU1+AU2+AU4+AU5+AU20",
        "body": "肩膀耸起、身体后倾、双手防御性前推",
        "camera_suggestion": "缓慢推进至面部特写，强调眼神恐惧",
    },
    "恐惧": {
        "low": "目光警觉、身体微微后倾",
        "medium": "呼吸急促、肩膀紧缩、目光四处游移",
        "high": "面色苍白、瞳孔收缩、身体蜷缩、双手抱头",
        "facs_au": "AU1+AU2+AU4+AU5+AU20+AU26",
        "body": "全身僵硬或蜷缩、防御姿态",
        "camera_suggestion": "手持晃动+推进，营造不安感",
    },
    "紧张": {
        "low": "短促眼神微调、下颌轻微收紧",
        "medium": "肩部僵硬、呼吸加快",
        "high": "手指无意识敲击、频繁吞咽、声音微颤",
        "facs_au": "AU4+AU7+AU23",
        "body": "坐立不安、搓手、频繁变换姿势",
        "camera_suggestion": "固定机位特写，强调微表情",
    },
    "焦虑": {
        "low": "目光游移、手指轻搓",
        "medium": "来回踱步、咬嘴唇、频繁看表",
        "high": "坐立不安、抓头发、语速加快、逻辑混乱",
        "facs_au": "AU1+AU4+AU15+AU17",
        "body": "来回走动、咬指甲、搓手、抖腿",
        "camera_suggestion": "手持跟拍，节奏不稳定",
    },
    "愤怒": {
        "low": "眉毛下压并靠拢、下颌收紧",
        "medium": "鼻翼轻扩、凝视固定",
        "high": "面部涨红、青筋暴起、双手握拳、身体前倾",
        "facs_au": "AU4+AU5+AU7+AU23",
        "body": "身体前倾、双手握拳、指向对方",
        "camera_suggestion": "低角度仰拍+推进，强化压迫感",
    },
    "暴怒": {
        "low": "咬紧牙关、太阳穴微鼓",
        "medium": "怒目圆睁、鼻翼大幅扩张",
        "high": "大吼、砸东西、身体剧烈动作、失去理智",
        "facs_au": "AU4+AU5+AU7+AU20+AU23+AU24",
        "body": "全身剧烈动作、砸击、推搡",
        "camera_suggestion": "快速推进+手持晃动，节奏爆发",
    },
    "悲伤": {
        "low": "目光低垂、嘴角微下垂",
        "medium": "眼眶泛红、嘴唇颤抖",
        "high": "泪流满面、声音哽咽、身体蜷缩",
        "facs_au": "AU1+AU4+AU15+AU17",
        "body": "肩膀塌下、低头、双手捂脸",
        "camera_suggestion": "缓慢推进至眼部特写，光线偏暗",
    },
    "绝望": {
        "low": "目光空洞、反应迟钝",
        "medium": "放弃姿态、不再挣扎",
        "high": "彻底崩溃、瘫软、失去所有希望的肢体语言",
        "facs_au": "AU1+AU4+AU15+AU17+AU25",
        "body": "瘫坐或瘫倒、双手垂落、目光失焦",
        "camera_suggestion": "固定机位+缓慢拉远，孤立感",
    },
    "厌恶": {
        "low": "鼻子轻微皱起",
        "medium": "上唇提升、眉头皱起",
        "high": "面部扭曲、转头回避、干呕",
        "facs_au": "AU9+AU10+AU15+AU17",
        "body": "身体后倾、双手推开、转头",
        "camera_suggestion": "特写面部，强调鼻唇动作",
    },
    "轻蔑": {
        "low": "嘴角单侧微扬",
        "medium": "单侧嘴角上扬+鼻翼微扩",
        "high": "冷笑、翻白眼、身体侧转",
        "facs_au": "AU14+AU10",
        "body": "身体侧转、下巴微抬、双手交叉",
        "camera_suggestion": "低角度拍摄，强调权力不对等",
    },
    "内疚": {
        "low": "短暂目光回避",
        "medium": "频繁低头、搓手、声音变小",
        "high": "无法直视、身体蜷缩、主动道歉姿态",
        "facs_au": "AU1+AU4+AU15",
        "body": "低头、双手绞在一起、身体蜷缩",
        "camera_suggestion": "俯拍+特写，强调渺小感",
    },
    "羞耻": {
        "low": "面部微红、目光回避",
        "medium": "用手遮脸、身体蜷缩",
        "high": "全身蜷缩、想要消失、哭泣",
        "facs_au": "AU1+AU4+AU15+AU25",
        "body": "双手捂脸、身体蜷缩成团",
        "camera_suggestion": "俯拍+缓慢拉远，暴露感",
    },

    # === 积极情绪 ===
    "开心": {
        "low": "嘴角微微上扬、眼角细纹",
        "medium": "笑容展开、眼睛发亮",
        "high": "开怀大笑、眼睛弯成月牙、面部肌肉放松",
        "facs_au": "AU6+AU12",
        "body": "身体放松、肩膀下沉、手势自然",
        "camera_suggestion": "平视或略高角度，柔和光线",
    },
    "兴奋": {
        "low": "眼睛发亮、嘴角上扬",
        "medium": "身体前倾、手势增多、语速加快",
        "high": "跳起来、大声说话、面部红润、全身充满能量",
        "facs_au": "AU6+AU12+AU25+AU26",
        "body": "身体前倾、手势夸张、可能跳跃",
        "camera_suggestion": "快速推进+环绕，节奏加快",
    },
    "温暖": {
        "low": "目光柔和、嘴角微扬",
        "medium": "眼神充满爱意、身体微微倾向对方",
        "high": "泪水含笑、紧紧拥抱、声音温柔",
        "facs_au": "AU6+AU12",
        "body": "身体倾向对方、轻触、拥抱",
        "camera_suggestion": "柔和侧光+缓慢推进，暖色调",
    },
    "平静": {
        "low": "面部表情自然、呼吸平稳",
        "medium": "目光平和、嘴角自然",
        "high": "完全放松、闭目养神、享受当下",
        "facs_au": "AU0",
        "body": "身体完全放松、姿态自然",
        "camera_suggestion": "固定机位+自然光，稳定构图",
    },
    "满足": {
        "low": "嘴角微扬、目光满足",
        "medium": "长舒一口气、身体后靠",
        "high": "闭眼微笑、全身放松、发出满足的叹息",
        "facs_au": "AU6+AU12",
        "body": "身体后靠、双手放松摊开",
        "camera_suggestion": "中景+暖光，稳定构图",
    },
    "自信": {
        "low": "目光坚定、下巴微抬",
        "medium": "挺胸抬头、手势有力",
        "high": "大步行走、目光直视、声音洪亮",
        "facs_au": "AU4+AU5+AU12",
        "body": "挺胸、肩膀打开、手势有力",
        "camera_suggestion": "低角度仰拍，强化权威感",
    },
    "骄傲": {
        "low": "嘴角上扬、头微抬",
        "medium": "挺胸、目光环视",
        "high": "昂首阔步、接受赞美、姿态夸张",
        "facs_au": "AU6+AU12+AU14",
        "body": "挺胸、肩膀后展、下巴抬起",
        "camera_suggestion": "低角度+稳定构图，权威感",
    },

    # === 复合/过渡情绪 ===
    "惊讶": {
        "low": "眉毛微挑、眼睛略睁大",
        "medium": "眉毛上扬、嘴巴微张",
        "high": "瞪大眼睛、嘴巴大张、身体后仰",
        "facs_au": "AU1+AU2+AU5+AU26",
        "body": "身体后仰、双手举起、嘴巴大张",
        "camera_suggestion": "快速推进至面部特写，捕捉瞬间反应",
    },
    "震惊": {
        "low": "短暂呆住、表情凝固",
        "medium": "眼睛瞪大、呼吸暂停",
        "high": "完全僵住、手中物品掉落、无法反应",
        "facs_au": "AU1+AU2+AU5+AU25+AU26",
        "body": "全身僵住、手中物品可能掉落",
        "camera_suggestion": "固定机位+慢动作，强调时间停滞",
    },
    "疑惑": {
        "low": "眉毛微皱、头微歪",
        "medium": "眉头紧锁、嘴角微撇",
        "high": "反复查看、摇头、手托下巴思考",
        "facs_au": "AU4+AU15",
        "body": "头歪向一侧、手托下巴、眯眼",
        "camera_suggestion": "中景+固定机位，给思考空间",
    },
    "犹豫": {
        "low": "目光游移、嘴唇微抿",
        "medium": "欲言又止、身体前倾又后退",
        "high": "反复犹豫、手伸出又缩回、内心挣扎外显",
        "facs_au": "AU4+AU15+AU23",
        "body": "身体前后摇摆、手伸出又缩回",
        "camera_suggestion": "固定机位+侧面角度，展示内心挣扎",
    },
    "坚定": {
        "low": "目光聚焦、嘴唇轻抿",
        "medium": "下巴微抬、身体前倾",
        "high": "大步向前、声音有力、手势果断",
        "facs_au": "AU4+AU5+AU23",
        "body": "身体前倾、手势有力、步伐坚定",
        "camera_suggestion": "低角度仰拍+推进，强化决心",
    },
    "无奈": {
        "low": "轻叹一口气、肩膀微塌",
        "medium": "摇头、双手摊开",
        "high": "长叹、身体后靠、闭眼",
        "facs_au": "AU1+AU15+AU17",
        "body": "肩膀塌下、双手摊开、摇头",
        "camera_suggestion": "中景+固定机位，留白空间",
    },
    "心虚": {
        "low": "短暂目光回避",
        "medium": "频繁眨眼、搓手",
        "high": "说话结巴、身体后退、手无处安放",
        "facs_au": "AU1+AU4+AU15+AU23",
        "body": "身体后退、手无处安放、频繁变换姿势",
        "camera_suggestion": "特写面部+侧面角度，强调回避",
    },
    "期待": {
        "low": "目光望向远方、嘴角微扬",
        "medium": "身体前倾、双手交握",
        "high": "坐立不安、频繁看时间、搓手",
        "facs_au": "AU6+AU12",
        "body": "身体前倾、双手交握或搓手",
        "camera_suggestion": "浅景深+缓慢推进，聚焦期待感",
    },
    "失落": {
        "low": "目光略暗、嘴角微垂",
        "medium": "低头、肩膀塌下",
        "high": "瘫坐、目光空洞、手中物品滑落",
        "facs_au": "AU1+AU4+AU15",
        "body": "肩膀塌下、低头、身体蜷缩",
        "camera_suggestion": "固定机位+缓慢拉远，孤立感",
    },
    "释然": {
        "low": "肩膀微微放松",
        "medium": "长舒一口气、嘴角微扬",
        "high": "闭眼微笑、身体完全放松、流泪但带笑",
        "facs_au": "AU6+AU12+AU25",
        "body": "肩膀下沉、身体放松、可能流泪",
        "camera_suggestion": "柔和光线+缓慢拉远，情绪释放",
    },
    "孤独": {
        "low": "目光望向窗外、反应迟钝",
        "medium": "独自一人时的空洞表情",
        "high": "蜷缩在角落、双手抱膝、无声哭泣",
        "facs_au": "AU1+AU4+AU15+AU17",
        "body": "蜷缩、双手抱膝、低头",
        "camera_suggestion": "大远景+固定机位，人物渺小",
    },
    "嫉妒": {
        "low": "目光追随某人、嘴角微抿",
        "medium": "咬嘴唇、拳头微握",
        "high": "怒视、摔东西、言语攻击",
        "facs_au": "AU4+AU7+AU23",
        "body": "身体僵硬、拳头握紧、怒视",
        "camera_suggestion": "特写面部+低角度，强调压迫感",
    },

    # === 社交/情境情绪 ===
    "害羞": {
        "low": "面部微红、目光回避",
        "medium": "低头微笑、手拨弄头发",
        "high": "捂脸、身体转向一侧、声音变小",
        "facs_au": "AU6+AU12+AU25",
        "body": "低头、手拨弄头发、身体侧转",
        "camera_suggestion": "柔和侧光+中景，温柔感",
    },
    "尴尬": {
        "low": "短暂沉默、嘴角抽动",
        "medium": "干笑、搓手、目光四处游移",
        "high": "想要逃离、语无伦次、面部涨红",
        "facs_au": "AU6+AU12+AU25",
        "body": "搓手、身体后退、想要逃离",
        "camera_suggestion": "固定机位+中景，留白尴尬空间",
    },
    "敬佩": {
        "low": "目光专注、微微点头",
        "medium": "身体前倾、眼睛发亮",
        "high": "鼓掌、站起、大声赞叹",
        "facs_au": "AU1+AU2+AU6",
        "body": "身体前倾、可能站起、手势表达赞叹",
        "camera_suggestion": "仰拍+推进，强化崇敬感",
    },
    "同情": {
        "low": "目光柔和、微微皱眉",
        "medium": "身体倾向对方、伸手轻触",
        "high": "拥抱对方、泪水含眶、声音温柔",
        "facs_au": "AU1+AU4",
        "body": "身体倾向对方、伸手轻触或拥抱",
        "camera_suggestion": "双人中景+柔光，温暖感",
    },
    "无聊": {
        "low": "目光呆滞、反应慢半拍",
        "medium": "打哈欠、玩手指",
        "high": "趴下、闭眼、完全不回应",
        "facs_au": "AU4+AU15",
        "body": "托腮、打哈欠、身体瘫软",
        "camera_suggestion": "固定机位+长停留，时间感",
    },
    "厌恶_社交": {
        "low": "礼貌性微笑但眼神冷淡",
        "medium": "身体微微后倾、减少回应",
        "high": "找借口离开、明显回避",
        "facs_au": "AU14",
        "body": "身体后倾、交叉双臂、回避目光",
        "camera_suggestion": "侧面角度，展示距离感",
    },
}


def get_emotion_motion(emotion: str, intensity: str = "medium") -> str:
    """返回标准化的情绪肢体描述。

    Args:
        emotion: 情绪名称（如"害怕"、"开心"）
        intensity: 强度级别（"low"、"medium"、"high"）

    Returns:
        标准化的情绪肢体描述
    """
    entry = EMOTION_MOTION_LIBRARY.get(emotion, {})
    return entry.get(intensity, entry.get("medium", ""))


def get_emotion_facs_au(emotion: str) -> str:
    """返回情绪对应的 FACS Action Unit 编码"""
    entry = EMOTION_MOTION_LIBRARY.get(emotion, {})
    return entry.get("facs_au", "")


def get_emotion_body(emotion: str) -> str:
    """返回情绪对应的身体语言描述"""
    entry = EMOTION_MOTION_LIBRARY.get(emotion, {})
    return entry.get("body", "")


def get_emotion_camera_suggestion(emotion: str) -> str:
    """返回情绪对应的镜头建议"""
    entry = EMOTION_MOTION_LIBRARY.get(emotion, {})
    return entry.get("camera_suggestion", "")


def list_all_emotions() -> list[str]:
    """返回所有可用的情绪名称"""
    return list(EMOTION_MOTION_LIBRARY.keys())


def list_emotions_by_category() -> dict[str, list[str]]:
    """按类别分组返回情绪列表"""
    negative = ["害怕", "恐惧", "紧张", "焦虑", "愤怒", "暴怒", "悲伤", "绝望", "厌恶", "轻蔑", "内疚", "羞耻"]
    positive = ["开心", "兴奋", "温暖", "平静", "满足", "自信", "骄傲"]
    compound = ["惊讶", "震惊", "疑惑", "犹豫", "坚定", "无奈", "心虚", "期待", "失落", "释然", "孤独", "嫉妒"]
    social = ["害羞", "尴尬", "敬佩", "同情", "无聊", "厌恶_社交"]
    return {
        "消极": [e for e in negative if e in EMOTION_MOTION_LIBRARY],
        "积极": [e for e in positive if e in EMOTION_MOTION_LIBRARY],
        "复合": [e for e in compound if e in EMOTION_MOTION_LIBRARY],
        "社交": [e for e in social if e in EMOTION_MOTION_LIBRARY],
    }
