"""Style Libraries — 视觉风格标准化映射。

参考来源：
- Wikipedia: Film Styles
- StudioBinder: Wes Anderson Style Guide
- No Film School: Kubrick vs Anderson
- Academia: Color Design in Wong Kar-wai Cinema
- Heart of Noir: Aesthetic of Noir
- Cyberpunk Redux (MDPI)
- Atlantis Press: Visual Characteristics of Cyberpunk Films
- Curzon Journal: Unpacking Wes Anderson's Style

核心思想：风格不是每次由 LLM 即兴描述，应使用标准化映射。
"""

# ============================================================
# 1. 导演视觉风格库
# ============================================================
DIRECTOR_STYLE_LIBRARY: dict[str, dict] = {
    "wes_anderson": {
        "name": "韦斯·安德森",
        "name_en": "Wes Anderson",
        "signature": "对称构图、暖色调、平面化构图、童话感",
        "camera": "固定机位为主、缓慢横摇、平面化运动",
        "lighting": "自然光+柔光，明亮温暖",
        "color": "暖色系（棕、黄、橙、粉）+高饱和度",
        "composition": "严格对称、居中构图、平面化（planimetric）",
        "editing": "跳切、快速剪辑、章节式结构",
        "typography": "Futura/Helvetica 字体、标题卡",
        "emotion_effect": "怀旧、温情、荒诞幽默、精致的忧伤",
        "usage": "童话叙事、家庭故事、荒诞喜剧、怀旧题材",
    },
    "kubrick": {
        "name": "斯坦利·库布里克",
        "name_en": "Stanley Kubrick",
        "signature": "单点透视对称、长镜头、极端景深、冷峻理性",
        "camera": "稳定器长镜头、缓慢推进、单点透视",
        "lighting": "自然光+高对比度，冷调",
        "color": "冷色系（蓝、灰、白）+去饱和",
        "composition": "严格单点透视、对称、几何感、景深极端",
        "editing": "长镜头、缓慢节奏",
        "emotion_effect": "冷峻、理性、不安、哲学深度",
        "usage": "科幻、战争、心理惊悚、哲学题材",
    },
    "wong_kar_wai": {
        "name": "王家卫",
        "name_en": "Wong Kar-wai",
        "signature": "抽帧/慢门模糊、霓虹光影、怀旧色调、情绪蒙太奇",
        "camera": "手持+抽帧（step printing）、慢门模糊、长焦压缩",
        "lighting": "霓虹灯、钨丝灯暖光、混合色温",
        "color": "霓虹色（绿、红、蓝）+高饱和+胶片颗粒",
        "composition": "倾斜构图、前景遮挡、窗户/门框框架、人物偏移中心",
        "editing": "抽帧模糊、情绪蒙太奇、非线性叙事",
        "emotion_effect": "怀旧、孤独、暧昧、时间流逝、都市疏离",
        "usage": "都市爱情、怀旧、情绪驱动叙事",
    },
    "hitchcock": {
        "name": "阿尔弗雷德·希区柯克",
        "name_en": "Alfred Hitchcock",
        "signature": "变焦推近（dolly zoom）、主观镜头、悬疑构图",
        "camera": "dolly zoom（希区柯克式变焦）、主观镜头、精确构图",
        "lighting": "低调照明、明暗对比",
        "color": "冷暖交错、关键道具高饱和",
        "composition": "不对称、倾斜、画中画、门框/窗框",
        "editing": "精确剪辑、悬念节奏",
        "emotion_effect": "悬疑、紧张、窥视感、心理压迫",
        "usage": "悬疑、惊悚、犯罪题材",
    },
    "nolan": {
        "name": "克里斯托弗·诺兰",
        "name_en": "Christopher Nolan",
        "signature": "IMAX大画幅、实拍特效、非线性叙事、时间折叠",
        "camera": "IMAX摄影机、实拍运动、大规模跟拍",
        "lighting": "自然光为主、高对比度",
        "color": "冷暖对比、去饱和+局部高饱和",
        "composition": "大画幅对称、几何感、建筑线条",
        "editing": "交叉剪辑、时间折叠、多线并行",
        "emotion_effect": "宏大、震撼、时间感、哲学思辨",
        "usage": "科幻大片、时间叙事、动作悬疑",
    },
    "tarantino": {
        "name": "昆汀·塔伦蒂诺",
        "name_en": "Quentin Tarantino",
        "signature": "低角度、脚部特写、长对话、暴力美学",
        "camera": "低角度、后备箱视角、环绕、长对话中景",
        "lighting": "高对比度、霓虹色彩、复古质感",
        "color": "高饱和、红黄绿强烈对比",
        "composition": "低角度+仰拍、脚部/腿部特写、画中画",
        "editing": "长对话段落+突然暴力切换",
        "emotion_effect": "黑色幽默、暴力美学、复古酷感",
        "usage": "犯罪、黑色喜剧、暴力美学",
    },
    "bong_joon_ho": {
        "name": "奉俊昊",
        "name_en": "Bong Joon-ho",
        "signature": "垂直空间隐喻、类型混搭、社会隐喻、精确调度",
        "camera": "垂直升降、跟拍、多层空间调度",
        "lighting": "自然光+环境光、对比不同阶层空间",
        "color": "阶层对比色（富人暖调、穷人冷调）",
        "composition": "垂直构图隐喻、楼梯/门窗框架、多层景深",
        "editing": "类型切换、节奏突变",
        "emotion_effect": "社会讽刺、黑色幽默、不安、阶层焦虑",
        "usage": "社会讽刺、类型混搭、阶级叙事",
    },
    "koreeda": {
        "name": "是枝裕和",
        "name_en": "Hirokazu Koreeda",
        "signature": "自然光长镜头、家庭日常、静谧观察、细腻情感",
        "camera": "固定/缓慢跟拍、自然光长镜头、中近景为主",
        "lighting": "自然光、柔和漫射光",
        "color": "淡雅自然色、去饱和、日系清透",
        "composition": "日常构图、门窗框架、生活化场景",
        "editing": "长镜头、缓慢节奏、省略叙事",
        "emotion_effect": "温暖、细腻、日常之美、淡淡忧伤",
        "usage": "家庭故事、日常叙事、情感剧",
    },
    "villeneuve": {
        "name": "丹尼斯·维伦纽瓦",
        "name_en": "Denis Villeneuve",
        "signature": "大画幅+低饱和、声音设计、建筑感构图、压迫性沉默",
        "camera": "IMAX/大画幅、缓慢推进、航拍、极端远景",
        "lighting": "自然光+极端环境光（沙漠/雾气）",
        "color": "极低饱和、单色调、橙蓝对比",
        "composition": "建筑感对称、极端远景+极特写交替、负空间",
        "editing": "缓慢节奏、长停留",
        "emotion_effect": "压迫、敬畏、孤独、史诗感",
        "usage": "科幻史诗、政治惊悚、末世题材",
    },
    "zhang_yimou": {
        "name": "张艺谋",
        "name_en": "Zhang Yimou",
        "signature": "浓烈色彩、大场面调度、民俗元素、视觉奇观",
        "camera": "大远景航拍、群体调度、对称构图",
        "lighting": "自然光+舞台化用光",
        "color": "浓烈对比色（红/黄/蓝）、高饱和",
        "composition": "大场面群像对称、建筑线条、自然景观",
        "editing": "慢镜头、仪式感节奏",
        "emotion_effect": "震撼、史诗感、民族文化、视觉奇观",
        "usage": "历史/武侠大片、民俗题材、视觉叙事",
    },
}


# ============================================================
# 2. 电影视觉风格/流派库
# ============================================================
VISUAL_STYLE_LIBRARY: dict[str, dict] = {
    "film_noir": {
        "name": "黑色电影",
        "name_en": "Film Noir",
        "signature": "低调照明、明暗对比、倾斜构图、城市夜景",
        "lighting": "low_key, chiaroscuro, 大量阴影、百叶窗投影",
        "color": "黑白为主（经典）；新黑色电影用冷蓝+霓虹",
        "camera": "dutch_angle, 低角度, 深焦摄影, 倾斜构图",
        "composition": "不对称、画中画、阴影分割画面、倾斜",
        "emotion_effect": "阴郁、宿命、道德模糊、城市孤独",
        "usage": "犯罪、侦探、悬疑、黑色幽默",
    },
    "neo_noir": {
        "name": "新黑色电影",
        "name_en": "Neo-Noir",
        "signature": "彩色+霓虹、城市夜景、道德模糊、视觉华丽",
        "lighting": "neon, low_key, 混合色温, 色彩对比",
        "color": "霓虹色（蓝/红/紫）+ 暗调",
        "camera": "手持+稳定器混合、倾斜、低角度",
        "composition": "霓虹反射、雨中倒影、玻璃/镜面",
        "emotion_effect": "都市迷幻、道德灰色、华丽颓废",
        "usage": "现代犯罪、赛博朋克、都市悬疑",
    },
    "cyberpunk": {
        "name": "赛博朋克",
        "name_en": "Cyberpunk",
        "signature": "霓虹+暗调、高科技低生活、垂直城市、全息投影",
        "lighting": "neon霓虹灯、混合色温、烟雾漫射",
        "color": "霓虹紫/蓝/粉 + 暗黑底色、高对比",
        "camera": "航拍城市、垂直俯瞰、手持+稳定器",
        "composition": "垂直层次（上层天堂/下层地狱）、全息广告叠加",
        "emotion_effect": "未来焦虑、科技异化、反乌托邦、视觉冲击",
        "usage": "科幻、反乌托邦、科技惊悚",
    },
    "gothic": {
        "name": "哥特风格",
        "name_en": "Gothic",
        "signature": "暗调、阴影、哥特建筑、神秘感、恐怖美学",
        "lighting": "low_key, 烛光, 月光, 极端明暗",
        "color": "深色系（黑/深红/深蓝）+ 金色点缀",
        "camera": "低角度、倾斜、缓慢推进",
        "composition": "哥特建筑线条、拱门/尖塔、阴影覆盖",
        "emotion_effect": "神秘、恐怖、浪漫、衰败之美",
        "usage": "恐怖、哥特爱情、暗黑奇幻",
    },
    "german_expressionism": {
        "name": "德国表现主义",
        "name_en": "German Expressionism",
        "signature": "极端阴影、扭曲几何、倾斜角度、情绪外化",
        "lighting": "极端明暗对比、手绘阴影、投影",
        "color": "黑白+高对比",
        "camera": "极端角度、倾斜、扭曲透视",
        "composition": "扭曲几何、倾斜线条、画中画",
        "emotion_effect": "焦虑、恐惧、心理扭曲、疯狂",
        "usage": "恐怖、心理惊悚、表现主义叙事",
    },
    "realism": {
        "name": "现实主义",
        "name_en": "Realism",
        "signature": "自然光、手持摄影、真实场景、纪实质感",
        "lighting": "natural, 自然环境光",
        "color": "去饱和、自然色调",
        "camera": "handheld, 跟拍, 观察式",
        "composition": "自然构图、不刻意美化",
        "emotion_effect": "真实、沉浸、纪录片质感",
        "usage": "社会题材、纪录片风格、写实剧情",
    },
    "minimalism": {
        "name": "极简主义",
        "name_en": "Minimalism",
        "signature": "简洁构图、大量留白、缓慢节奏、克制叙事",
        "lighting": "柔和自然光、均匀照明",
        "color": "低饱和、素雅色调、单色系",
        "camera": "固定机位、长镜头、极少运动",
        "composition": "极简、留白、负空间、几何感",
        "emotion_effect": "静谧、内省、克制、诗意",
        "usage": "文艺片、慢电影、哲学叙事",
    },
    "baroque": {
        "name": "巴洛克风格",
        "name_en": "Baroque",
        "signature": "华丽装饰、强烈明暗、动态构图、戏剧性",
        "lighting": "chiaroscuro明暗对比、烛光、舞台化用光",
        "color": "浓烈深色（金/红/深蓝）+ 高饱和",
        "camera": "运动复杂、升降、环绕",
        "composition": "华丽装饰、动态对角线、多层景深",
        "emotion_effect": "华丽、戏剧性、权力、奢华",
        "usage": "宫廷剧、历史大片、宗教题材",
    },
    "pop_art": {
        "name": "波普艺术风格",
        "name_en": "Pop Art Style",
        "signature": "高饱和色彩、平面化、重复图案、商业美学",
        "lighting": "高调照明、均匀明亮",
        "color": "高饱和对比色（红/黄/蓝/粉）",
        "camera": "固定机位、平面化构图",
        "composition": "平面化、对称、重复、网格",
        "emotion_effect": "活泼、讽刺、商业感、视觉冲击",
        "usage": "MV、广告风格、喜剧、讽刺",
    },
    "surrealism": {
        "name": "超现实主义",
        "name_en": "Surrealism",
        "signature": "梦境逻辑、非理性组合、变形、象征",
        "lighting": "混合光源、不自然光效",
        "color": "梦幻色调、不自然色彩",
        "camera": "流畅运动、变形镜头",
        "composition": "非理性并置、梦境空间、变形透视",
        "emotion_effect": "梦幻、不安、荒诞、潜意识",
        "usage": "梦境叙事、心理探索、艺术电影",
    },
    "wuxia": {
        "name": "武侠美学",
        "name_en": "Wuxia Aesthetics",
        "signature": "飘逸动作、慢镜头、自然景观、东方意境",
        "lighting": "自然光+逆光剪影、黄金时段",
        "color": "浓烈自然色（红叶/白雪/青山）+ 高饱和",
        "camera": "航拍+跟拍、慢镜头、威亚运动",
        "composition": "自然景观大远景、人物渺小、留白意境",
        "emotion_effect": "豪迈、飘逸、东方诗意、江湖孤独",
        "usage": "武侠、古装动作、东方奇幻",
    },
    "retro_futurism": {
        "name": "复古未来主义",
        "name_en": "Retro-futurism",
        "signature": "过去想象的未来、模拟科技美学、怀旧+科幻",
        "lighting": "暖调+霓虹、CRT屏幕光",
        "color": "暖橙/棕+霓虹色、胶片质感",
        "camera": "对称构图、固定机位",
        "composition": "模拟设备、复古界面、对称空间",
        "emotion_effect": "怀旧未来感、温暖科技、复古酷",
        "usage": "科幻怀旧、 alternate history",
    },
    "grindhouse": {
        "name": "剥削电影风格",
        "name_en": "Grindhouse",
        "signature": "胶片磨损、颗粒感、高对比、B级片美学",
        "lighting": "硬光、高对比、不均匀",
        "color": "高饱和+偏色、胶片褪色感",
        "camera": "手持、快速变焦、不稳定",
        "composition": "粗糙、不精确、功能优先",
        "emotion_effect": "粗粝、生猛、暴力、怀旧",
        "usage": "动作、恐怖、B级片、复古致敬",
    },
}


# ============================================================
# 3. 色彩情绪映射库
# ============================================================
COLOR_PALETTE_LIBRARY: dict[str, dict] = {
    "warm_nostalgic": {
        "name": "暖调怀旧",
        "colors": ["琥珀", "赭石", "奶油白", "焦糖棕", "暖黄"],
        "hex_examples": ["#D4A574", "#8B6914", "#FFFDD0", "#C4A484", "#FFD700"],
        "emotion": "怀旧、温暖、回忆、家庭",
    },
    "cold_isolation": {
        "name": "冷调孤立",
        "colors": ["钢蓝", "冰灰", "银白", "暗紫", "深灰蓝"],
        "hex_examples": ["#4682B4", "#708090", "#F0F0F0", "#483D8B", "#2F4F4F"],
        "emotion": "孤独、疏离、寒冷、理性",
    },
    "neon_urban": {
        "name": "霓虹都市",
        "colors": ["霓虹粉", "电光蓝", "酸性绿", "紫罗兰", "深黑"],
        "hex_examples": ["#FF6B9D", "#00BFFF", "#39FF14", "#8A2BE2", "#0D0D0D"],
        "emotion": "都市、未来、夜生活、能量",
    },
    "earthy_natural": {
        "name": "大地自然",
        "colors": ["橄榄绿", "泥土棕", "天蓝", "麦穗黄", "石板灰"],
        "hex_examples": ["#808000", "#8B4513", "#87CEEB", "#F5DEB3", "#708090"],
        "emotion": "自然、朴素、田园、平静",
    },
    "dramatic_contrast": {
        "name": "戏剧对比",
        "colors": ["纯黑", "纯白", "深红", "金色", "暗影"],
        "hex_examples": ["#000000", "#FFFFFF", "#8B0000", "#FFD700", "#1a1a1a"],
        "emotion": "权力、戏剧性、仪式感、冲突",
    },
    "pastel_dream": {
        "name": "柔和梦幻",
        "colors": ["粉蓝", "薄荷绿", "淡紫", "奶油粉", "鹅黄"],
        "hex_examples": ["#B0E0E6", "#98FB98", "#DDA0DD", "#FFDAB9", "#FFFACD"],
        "emotion": "梦幻、温柔、少女感、轻盈",
    },
    "dark_gothic": {
        "name": "暗黑哥特",
        "colors": ["深黑", "暗红", "深紫", "骨白", "铁灰"],
        "hex_examples": ["#0A0A0A", "#4A0000", "#2E0854", "#F5F5F0", "#363636"],
        "emotion": "神秘、恐怖、衰败、暗黑浪漫",
    },
    "vibrant_pop": {
        "name": "活力波普",
        "colors": ["柠檬黄", "珊瑚红", "宝蓝", "翠绿", "亮橙"],
        "hex_examples": ["#FFF44F", "#FF6B6B", "#0047AB", "#50C878", "#FF8C00"],
        "emotion": "活力、年轻、乐观、商业",
    },
    "muted_melancholy": {
        "name": "低饱和忧郁",
        "colors": ["灰蓝", "褪色粉", "烟灰", "旧米", "暗橄榄"],
        "hex_examples": ["#6B8BA4", "#D4A5A5", "#808080", "#F0E6D3", "#556B2F"],
        "emotion": "忧郁、怀旧、克制、日常诗意",
    },
    "monochrome": {
        "name": "单色系",
        "colors": ["纯黑", "深灰", "中灰", "浅灰", "纯白"],
        "hex_examples": ["#000000", "#404040", "#808080", "#C0C0C0", "#FFFFFF"],
        "emotion": "极简、理性、抽象、形式感",
    },
}


# ============================================================
# 4. 构图规则库
# ============================================================
COMPOSITION_LIBRARY: dict[str, dict] = {
    "rule_of_thirds": {
        "name": "三分法",
        "name_en": "Rule of Thirds",
        "description": "将画面分为3×3网格，主体放在交叉点",
        "usage": "最常用构图法，平衡、自然、有呼吸感",
    },
    "center_frame": {
        "name": "居中构图",
        "name_en": "Center Framing",
        "description": "主体放在画面正中央",
        "usage": "对称感、正式感、Wes Anderson式、仪式感",
    },
    "symmetry": {
        "name": "对称构图",
        "name_en": "Symmetrical Composition",
        "description": "画面左右或上下对称",
        "usage": "平衡、秩序、建筑感、Kubrick/Anderson式",
    },
    "golden_ratio": {
        "name": "黄金比例",
        "name_en": "Golden Ratio",
        "description": "主体放在约1:1.618的比例位置",
        "usage": "经典美学比例、和谐感",
    },
    "leading_lines": {
        "name": "引导线",
        "name_en": "Leading Lines",
        "description": "利用场景中的线条引导视线到主体",
        "usage": "深度感、引导注意力、走廊/道路/栏杆",
    },
    "frame_within_frame": {
        "name": "画中画",
        "name_en": "Frame within Frame",
        "description": "利用门窗/窗框/镜子创造二级框架",
        "usage": "窥视感、层次感、隔离感、Wong Kar-wai式",
    },
    "negative_space": {
        "name": "负空间/留白",
        "name_en": "Negative Space",
        "description": "主体只占画面小部分，大量留白",
        "usage": "孤独感、极简、文艺片、呼吸感",
    },
    "diagonal": {
        "name": "对角线构图",
        "name_en": "Diagonal Composition",
        "description": "主体或线条沿对角线分布",
        "usage": "动态感、不稳定、紧张、运动感",
    },
    "foreground_interest": {
        "name": "前景兴趣",
        "name_en": "Foreground Interest",
        "description": "前景放置元素增加深度感",
        "usage": "景深层次、空间感、窥视感",
    },
    "depth_of_field": {
        "name": "景深控制",
        "name_en": "Depth of Field",
        "description": "利用浅景深/深景深控制注意力",
        "usage": "浅景深=主体聚焦、深景深=环境叙事",
    },
    "planimetric": {
        "name": "平面化构图",
        "name_en": "Planimetric Composition",
        "description": "背景与主体平行，画面趋于二维",
        "usage": "Wes Anderson式、绘本感、舞台感",
    },
    "geometric": {
        "name": "几何构图",
        "name_en": "Geometric Composition",
        "description": "利用三角形/圆形/方形等几何形状组织画面",
        "usage": "建筑感、秩序感、Kubrick式",
    },
}


# ============================================================
# 5. 画幅比例库
# ============================================================
ASPECT_RATIO_LIBRARY: dict[str, dict] = {
    "16:9": {
        "name": "16:9 宽屏",
        "usage": "标准高清、电视剧、流媒体",
        "emotion": "标准、自然、当代感",
    },
    "2.39:1": {
        "name": "2.39:1 变形宽银幕",
        "usage": "电影大片、史诗感、太空/风景",
        "emotion": "宏大、史诗、沉浸、电影感",
    },
    "1.85:1": {
        "name": "1.85:1 美国标准宽银幕",
        "usage": "好莱坞主流电影",
        "emotion": "标准电影感、叙事舒适",
    },
    "4:3": {
        "name": "4:3 学院比例",
        "usage": "老电影、文艺片、纪录片",
        "emotion": "怀旧、亲密、纪实、复古",
    },
    "1:1": {
        "name": "1:1 正方形",
        "usage": "社交媒体、MV、艺术短片",
        "emotion": "现代、社交、精致、艺术",
    },
    "9:16": {
        "name": "9:16 竖屏",
        "usage": "手机竖屏短剧、短视频、Reels",
        "emotion": "移动端、沉浸、亲密、竖屏短剧",
    },
    "2.76:1": {
        "name": "2.76:1 Ultra Panavision 70",
        "usage": "超级宽银幕（如《黄金三镖客》）",
        "emotion": "极致史诗、视觉奇观",
    },
    "1.19:1": {
        "name": "1.19:1 Movietone",
        "usage": "早期有声电影",
        "emotion": "复古、默片感",
    },
}


def get_director_style(director: str) -> dict:
    """获取导演视觉风格"""
    return DIRECTOR_STYLE_LIBRARY.get(director, {})


def get_visual_style(style: str) -> dict:
    """获取视觉风格/流派"""
    return VISUAL_STYLE_LIBRARY.get(style, {})


def get_color_palette(palette: str) -> dict:
    """获取色彩情绪映射"""
    return COLOR_PALETTE_LIBRARY.get(palette, {})


def get_composition_rule(rule: str) -> dict:
    """获取构图规则"""
    return COMPOSITION_LIBRARY.get(rule, {})


def list_all_directors() -> list[str]:
    """列出所有可用导演风格"""
    return list(DIRECTOR_STYLE_LIBRARY.keys())


def list_all_visual_styles() -> list[str]:
    """列出所有可用视觉风格"""
    return list(VISUAL_STYLE_LIBRARY.keys())


def list_all_color_palettes() -> list[str]:
    """列出所有可用色彩方案"""
    return list(COLOR_PALETTE_LIBRARY.keys())
