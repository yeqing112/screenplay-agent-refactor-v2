/**
 * Mock data for UI prototyping. All data is self-contained and does not depend on any backend.
 */

export const MOCK_BOOK = {
  id: 8,
  title: '最大的傲慢',
  chapters: 1,
  words: 178,
  created_at: '2026-06-22T03:01:04.798446',
}

export const MOCK_BIBLE = `世界观：当代都市背景，地点为普通中国二线城市道路边。
基调：温情现实主义，底层与中产阶级的碰撞，通过日常小事揭示深刻人性。
核心冲突：社会阶层差异带来的偏见与误解，最终靠真诚善意化解。
时代：2000 年代至 2020 年代，手机支付、共享单车等现代元素自然出现。`

export const MOCK_SCRIPTS = [
  {
    episode: 1,
    content: `【第 1 集：最大的傲慢】
场景：城市道路边

一个衣着朴素的老头，约 70 岁，推着一辆生锈的三轮车，车斗里装着几个废纸箱。
老头擦着汗，小声嘀咕：“这年头，收废品也越来越难做了。”

一辆黑色路虎从他身边疾驰而过，刺耳喇叭声划破街道。
老头皱起眉：“按什么按，没看见老人家在走路吗？”

路虎停在不远处，一个中年男人下车，一边打电话一边走近。
“我跟你说啊老李，我儿子这次考试又是全班第一……”

他收起电话，瞥了老头一眼，语气里满是不耐烦：
“老头，你这三轮车挡道了，挪一挪。”

老头抬眼看了他一眼，不急不慢地从怀里摸出一把车钥匙。
“年轻人，知道这车钥匙是什么样的吗？”

路虎车主不屑地笑了笑：
“你一个收破烂的，在我面前摆什么谱？”

老头没争辩，只是按下钥匙。旁边另一辆黑色轿车的车灯闪了一下。
“这车，在你眼里值不值钱？”

路虎车主愣住了。`,
    stage_directions: '路边 → 三轮车旁 → 路虎旁',
  },
]

export const MOCK_STORYBOARD = {
  episodeShots: {
    1: [
      {
        shot_id: '1-1',
        scene_name: '城市道路边',
        duration: 3,
        camera_angle: '全景',
        camera_movement: '固定',
        transition: '硬切',
        lighting: '自然光，明亮',
        bgm_mood: '平淡铺陈',
        sound_effects: ['车流声', '环境底噪'],
        dialogue: '',
        start_state: '老头推着三轮车上场',
        action_process: '缓慢前行，衣角随步伐轻微晃动',
        end_state: '停在路边调整呼吸',
        visual_prompt_static: '城市道路边，一位约七十岁的老头穿着深色旧夹克，推着生锈的三轮车，背景是灰白居民楼与行道树，午后自然光，写实电影感。',
        visual_prompt_motion: '固定机位，老头从画面右侧缓慢推车进入，链条轻响，车斗里的纸箱轻微晃动。',
        makeup_prompts: [
          {
            character_name: '老头',
            refined_outfit: '深色旧夹克、宽松黑裤、老式布鞋',
            refined_accessories: '草帽',
            makeup_spec: '老年妆，皱纹明显，皮肤略显粗糙',
            hair_style: '花白短发',
            visual_prompt_zh: '六宫格人物定妆：正面、侧面、四分之三肖像与全身视角统一展示同一位七十岁中国老人，质朴、疲惫但坚韧，背景纯净，写实影视定妆风格。',
          },
          {
            character_name: '路虎车主',
            refined_outfit: '蓝色 Polo 衫、深卡其休闲裤、皮鞋',
            refined_accessories: '太阳镜、腕表',
            makeup_spec: '中年男性，面容整洁',
            hair_style: '短发整齐',
            visual_prompt_zh: '六宫格人物定妆：四十岁中国中年男性，体面、自信，服装整洁，带轻微优越感，纯净背景，写实影视人物设定图。',
          },
        ],
        scene_prompt: '现代中国二线城市道路边，灰白楼体、行道树、水泥路面和普通路边设施共同构成真实日常街景。',
      },
      {
        shot_id: '1-2',
        scene_name: '城市道路边',
        duration: 4,
        camera_angle: '中景',
        camera_movement: '摇镜',
        transition: '硬切',
        lighting: '自然光',
        bgm_mood: '轻微紧张',
        sound_effects: ['汽车喇叭声'],
        dialogue: '老头：“按什么按，没看见老人家在走路吗？”',
        start_state: '老头停下脚步，看向路虎方向',
        action_process: '人物转身，表情从困惑变成不满',
        end_state: '盯住停下的路虎',
        visual_prompt_static: '老头转头看向画外的黑色路虎，神情克制却不悦，背景街道略虚化，焦点压在人物表情上。',
        visual_prompt_motion: '镜头从老头侧脸缓慢摇向路虎停车方向，带出人物视线和紧张气氛。',
        makeup_prompts: [],
        scene_prompt: '',
      },
      {
        shot_id: '1-3',
        scene_name: '城市道路边',
        duration: 5,
        camera_angle: '近景',
        camera_movement: '手持微晃',
        transition: '硬切',
        lighting: '高亮日光',
        bgm_mood: '对立升级',
        sound_effects: ['关车门声', '脚步声'],
        dialogue: '路虎车主：“老头，你三轮车挡道了，挪一挪。”',
        start_state: '路虎车主下车走近',
        action_process: '步伐自信，目光上下打量老头',
        end_state: '站到老头面前，保持压迫距离',
        visual_prompt_static: '路虎车主居高临下看着老头，神情轻蔑，背后是锃亮的黑色路虎，形成强烈身份反差。',
        visual_prompt_motion: '手持镜头跟随路虎车主下车、关门、逼近，镜头略带压迫感。',
        makeup_prompts: [],
        scene_prompt: '',
      },
      {
        shot_id: '1-4',
        scene_name: '城市道路边',
        duration: 6,
        camera_angle: '特写',
        camera_movement: '缓慢推进',
        transition: '硬切',
        lighting: '高反差',
        bgm_mood: '悬念抬升',
        sound_effects: ['钥匙碰撞声'],
        dialogue: '老头：“年轻人，知道这车钥匙是什么样的吗？”',
        start_state: '老头平静看着路虎车主',
        action_process: '伸手入怀，缓慢取出钥匙，举到对方面前',
        end_state: '钥匙停在半空，情绪反转前夜',
        visual_prompt_static: '老头粗糙的手举着一把车钥匙特写，逆光勾边，背景虚化，强调钥匙和老人手部纹理。',
        visual_prompt_motion: '镜头从钥匙特写慢慢拉到老人脸部，突出平静与笃定。',
        makeup_prompts: [],
        scene_prompt: '',
      },
      {
        shot_id: '1-5',
        scene_name: '城市道路边',
        duration: 4,
        camera_angle: '中景',
        camera_movement: '震动切换',
        transition: '硬切',
        lighting: '日光正常',
        bgm_mood: '戏剧反转',
        sound_effects: ['车辆解锁声'],
        dialogue: '',
        start_state: '路虎车主仍然不屑',
        action_process: '老头按下钥匙，旁边黑色轿车车灯亮起',
        end_state: '路虎车主愣在原地',
        visual_prompt_static: '按下钥匙的瞬间，旁边黑色轿车灯光闪烁，路虎车主从轻蔑转为震惊，形成戏剧反差。',
        visual_prompt_motion: '快速切换老人按钥匙、远处轿车亮灯、两人表情变化，制造反转节奏。',
        makeup_prompts: [],
        scene_prompt: '',
      },
    ],
  },
}

export const MOCK_VISUAL = {
  era: {
    timeline_start: '2000 年代（当代）',
    timeline_end: '2020 年代（当代）',
    clothing_spec: '老头偏底层劳动者装束，深色旧衣、布鞋、草帽；路虎车主偏体面中产，Polo 衫、休闲裤、皮鞋与腕表。',
    color_palette: '整体以灰蓝、土黄、金属黑为主，城市环境偏冷，反转后情绪逐渐转暖。',
    architecture_spec: '普通中国二线城市道路边，多层居民楼、临街店铺、行道树、电线杆和垃圾桶构成生活化背景。',
    color_curve: '前段冷静克制，中段对立升级，后段以反转带出温情余韵。',
  },
  locations: [
    {
      name: '城市道路边',
      category: '户外/街道',
      style: '现实主义、普通日常',
      description: '普通二线城市道路边，人行道与非机动车道相邻，灰色水泥路面，行道树和路边停车共同构成生活街景。',
      color_palette: '灰白、灰蓝、点缀绿色',
      lighting_mood: '自然日光，明亮但不过曝',
      era: '当代，2020 年代',
      en_prompt: 'Four wide street views of a Chinese roadside scene with cement sidewalk, apartment blocks, street trees, parked cars, bright daylight, realistic cinematic mood.',
      zh_prompt: '城市道路边场景设定图，展示灰白居民楼、行道树、水泥路面和路边停车，整体写实、生活化、带轻微冷色调。',
      visual_prompt_zh: '当代城市道路边实景，灰色路面与行道树并置，普通居民楼和停放车辆构成低调真实的生活感。',
    },
  ],
  props: [
    {
      name: '黑色路虎越野车',
      category: '交通工具',
      importance: 'medium',
      era: '当代，2020 年代',
      description: '一辆黑色路虎 SUV，车身较高，黑色金属漆，深色车窗，轮毂干净，给人中产体面感。',
      en_prompt: 'A black Land Rover style SUV shown in multiple clean product views on white background, realistic material and proportions.',
      zh_prompt: '黑色路虎越野车多角度道具图，黑色金属漆面，深色车窗，写实产品展示风格。',
    },
    {
      name: '生锈三轮车',
      category: '交通工具',
      importance: 'high',
      era: '当代，2020 年代',
      description: '老旧载货三轮车，车斗有锈迹，链条略松，轮胎磨损，车斗中放着废纸箱。',
      en_prompt: 'A rusty old cargo tricycle with worn tires, loose chain and cardboard boxes in the rear cargo compartment.',
      zh_prompt: '生锈三轮车多角度道具图，金属锈迹明显，结构老旧，带废纸箱，写实展示风格。',
    },
    {
      name: '车钥匙',
      category: '信物/关键道具',
      importance: 'high',
      era: '当代，2020 年代',
      description: '一把黑色智能车钥匙，塑料外壳，按键式遥控结构，是剧情反转的关键细节。',
      en_prompt: 'A black smart car key fob shown in clean product views, realistic plastic shell and clear button layout.',
      zh_prompt: '黑色车钥匙多角度道具图，塑料外壳，按键清晰，写实产品拍摄质感。',
    },
  ],
  makeups: [
    {
      episode: 1,
      character_name: '老头',
      gender: '男性',
      identity: '约 70 岁，收废品老人',
      temperament: '朴素、隐忍、底层劳动者、倔强',
      appearance: '满脸深皱纹，皮肤粗糙偏黑，眼窝深陷，双手粗糙有劳动痕迹。',
      refined_outfit: '深色旧夹克、宽松黑裤、老式布鞋',
      refined_accessories: '草帽（可带破边）',
      makeup_spec: '老年妆明显，法令纹和眼下细纹突出，嘴唇略干裂。',
      hair_style: '花白短发，略显凌乱',
      visual_prompt_zh: '六宫格人物定妆：七十岁中国老人，朴素、坚韧、略显疲惫，服装统一，纯净背景，影视级写实质感。',
    },
    {
      episode: 1,
      character_name: '路虎车主',
      gender: '男性',
      identity: '约 40 岁，中产车主',
      temperament: '自信、体面、优越感明显',
      appearance: '面容整洁，眉骨较高，轻微法令纹，眼神带压迫感。',
      refined_outfit: '蓝色 Polo 衫、深卡其休闲裤、深棕皮鞋',
      refined_accessories: '太阳镜、金属腕表',
      makeup_spec: '整体干净利落，保持都市中年男性的体面感。',
      hair_style: '短发整齐，发际线略后移',
      visual_prompt_zh: '六宫格人物定妆：四十岁中国中年男性，着装体面，神态自信，略带轻蔑，纯净背景，影视写实风格。',
    },
  ],
}

export const MOCK_QA = [
  {
    episode: 1,
    error_count: 0,
    result: {
      overall_score: 9.2,
      scores: {
        story: 9.5,
        character: 9.0,
        dialogue: 9.5,
        pacing: 8.5,
        structure: 9.0,
      },
      high_errors: [],
      medium_errors: [],
      suggestions: ['第一句独白可以再自然一点，用动作和停顿替代部分直白说明。'],
    },
  },
]

function makeMockImageUrl(name: string, palette: string): string {
  const size = 400
  const bg = '#1e293b'
  const cardBg = '#0f172a'
  const border = '#334155'
  const textColor = '#64748b'
  const accent = palette === 'purple' ? '#a855f7' : palette === 'green' ? '#22c55e' : '#3b82f6'
  const modelName = accent === '#a855f7' ? 'Seedream' : accent === '#22c55e' ? 'DALL-E 3' : 'Midjourney'

  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${Math.floor(size * 0.75)}" viewBox="0 0 ${size} ${Math.floor(size * 0.75)}">
      <rect width="${size}" height="${Math.floor(size * 0.75)}" fill="${bg}"/>
      <rect x="16" y="16" width="${size - 32}" height="${Math.floor(size * 0.75) - 32}" rx="8" fill="${cardBg}" stroke="${border}" stroke-width="1"/>
      <rect x="40" y="40" width="${size - 80}" height="${Math.floor(size * 0.5) - 60}" rx="6" fill="#0a0e1a" stroke="${border}" stroke-width="1"/>
      <text x="${size / 2}" y="${Math.floor(size * 0.4)}" fill="${textColor}" font-size="12" text-anchor="middle" font-family="monospace">示意图 ${name}</text>
      <text x="${size / 2}" y="${Math.floor(size * 0.45)}" fill="${accent}" font-size="10" text-anchor="middle" font-family="monospace">${modelName}</text>
    </svg>`,
  )}`
}

export type MockAssetImage = {
  id: string
  source_type: 'scene' | 'prop' | 'makeup'
  source_name: string
  model_name: string
  prompt_type: 'zh' | 'en'
  image_url: string
  created_at: string
  is_favorite: boolean
}

export const MOCK_GENERATED_IMAGES: MockAssetImage[] = [
  { id: 'img-1', source_type: 'scene', source_name: '城市道路边', model_name: 'Seedream 4.5', prompt_type: 'zh', image_url: makeMockImageUrl('城市道路边 ZH', 'purple'), created_at: '2026-06-22T20:15:00', is_favorite: false },
  { id: 'img-2', source_type: 'scene', source_name: '城市道路边', model_name: 'DALL-E 3', prompt_type: 'en', image_url: makeMockImageUrl('城市道路边 EN', 'green'), created_at: '2026-06-22T20:16:00', is_favorite: true },
  { id: 'img-3', source_type: 'prop', source_name: '黑色路虎越野车', model_name: 'Seedream 4.5', prompt_type: 'zh', image_url: makeMockImageUrl('路虎 ZH', 'purple'), created_at: '2026-06-22T20:20:00', is_favorite: false },
  { id: 'img-4', source_type: 'prop', source_name: '黑色路虎越野车', model_name: 'DALL-E 3', prompt_type: 'en', image_url: makeMockImageUrl('路虎 EN', 'blue'), created_at: '2026-06-22T20:21:00', is_favorite: true },
  { id: 'img-5', source_type: 'prop', source_name: '车钥匙', model_name: 'Seedream 4.5', prompt_type: 'zh', image_url: makeMockImageUrl('车钥匙 ZH', 'purple'), created_at: '2026-06-22T20:22:00', is_favorite: false },
  { id: 'img-6', source_type: 'makeup', source_name: '老头', model_name: 'Seedream 4.5', prompt_type: 'zh', image_url: makeMockImageUrl('老头定妆', 'purple'), created_at: '2026-06-22T20:25:00', is_favorite: false },
  { id: 'img-7', source_type: 'makeup', source_name: '路虎车主', model_name: 'DALL-E 3', prompt_type: 'zh', image_url: makeMockImageUrl('路虎车主定妆', 'green'), created_at: '2026-06-22T20:26:00', is_favorite: false },
]

export function delay(ms = 300) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
