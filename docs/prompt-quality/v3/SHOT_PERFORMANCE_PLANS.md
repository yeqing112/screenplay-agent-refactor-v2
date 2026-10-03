# Shot Performance Plans V3

## SH_E01_SC001_001

```json
{
  "shot_id": "SH_E01_SC001_001",
  "duration": 5.0,
  "characters": [
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "售票员",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "林晚",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "林晚",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "售票员",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "林晚",
      "body_action": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "林晚头部只做与信息接收对应的轻微转动",
      "eye_action": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_action": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "售票员",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "林晚",
      "body_action": "林晚完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "售票员",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "售票员",
      "body_action": "售票员完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "林晚",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "林晚",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "售票员",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "林晚",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    },
    {
      "actor": "售票员",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "林晚",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    },
    {
      "actor": "售票员",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "林晚",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    },
    {
      "actor": "售票员",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "林晚",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    },
    {
      "actor": "售票员",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "林晚",
      "target": "售票员",
      "action": "林晚在售票窗口完成购票并留意周围"
    }
  ],
  "prop_interaction": [
    {
      "prop": "TICKET",
      "state": "林晚正在查看"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "继续静止保持"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "售票员": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "车票": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC001_002

```json
{
  "shot_id": "SH_E01_SC001_002",
  "duration": 5.0,
  "characters": [
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚肩膀保持不动，右脚不移动，身体只在胸口出现极轻的停顿",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "眼球先向站台右上方移动，约半秒后头部抬起五度",
      "eye_direction": "视线从车票移到站台红伞，最后固定在伞骨区域",
      "facial_emotion": "眉间从平展变为轻微收紧，嘴唇从闭合变为略微分开",
      "hand_pose": "右手拇指压住车票边角，看到异常后手指停止摩擦",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "林晚",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "林晚",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "右手拇指压住车票边角，看到异常后手指停止摩擦",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "当前线索",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "林晚",
      "body_action": "林晚肩膀保持不动，右脚不移动，身体只在胸口出现极轻的停顿",
      "hand_action": "右手拇指压住车票边角，看到异常后手指停止摩擦",
      "head_action": "眼球先向站台右上方移动，约半秒后头部抬起五度",
      "eye_action": "视线从车票移到站台红伞，最后固定在伞骨区域",
      "facial_action": "眉间从平展变为轻微收紧，嘴唇从闭合变为略微分开",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "当前线索",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "林晚",
      "body_action": "林晚完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "当前线索",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "保持对线索的注视",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "林晚",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "林晚",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "当前线索",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "林晚",
      "detail": "右手拇指压住车票边角，看到异常后手指停止摩擦"
    }
  ],
  "head_movement": [
    {
      "actor": "林晚",
      "detail": "眼球先向站台右上方移动，约半秒后头部抬起五度"
    }
  ],
  "eye_movement": [
    {
      "actor": "林晚",
      "detail": "视线从车票移到站台红伞，最后固定在伞骨区域"
    }
  ],
  "facial_changes": [
    {
      "actor": "林晚",
      "detail": "眉间从平展变为轻微收紧，嘴唇从闭合变为略微分开"
    }
  ],
  "interaction_beats": [
    {
      "actor": "林晚",
      "target": "prop",
      "action": "林晚看见站台上的红伞"
    }
  ],
  "prop_interaction": [
    {
      "prop": "RED_UMBRELLA",
      "state": "关键视觉线索"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "轻微重新构图"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "红伞": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC001_003

```json
{
  "shot_id": "SH_E01_SC001_003",
  "duration": 5.0,
  "characters": [
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "顾沉",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "林晚",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "林晚",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "顾沉",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "林晚",
      "body_action": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "林晚头部只做与信息接收对应的轻微转动",
      "eye_action": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_action": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "顾沉",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "林晚",
      "body_action": "林晚完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "顾沉",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "顾沉",
      "body_action": "顾沉完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "林晚",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "林晚",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "顾沉",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "林晚",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    },
    {
      "actor": "顾沉",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "林晚",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    },
    {
      "actor": "顾沉",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "林晚",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    },
    {
      "actor": "顾沉",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "林晚",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    },
    {
      "actor": "顾沉",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "林晚",
      "target": "顾沉",
      "action": "林晚与顾沉确认折断的伞骨"
    }
  ],
  "prop_interaction": [
    {
      "prop": "BROKEN_UMBRELLA_RIB",
      "state": "证据状态"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "继续静止保持"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "顾沉": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "折断的红伞伞骨": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC001_004

```json
{
  "shot_id": "SH_E01_SC001_004",
  "duration": 5.0,
  "characters": [
    {
      "identity": "顾沉",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "顾沉保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "顾沉头部只做与信息接收对应的轻微转动",
      "eye_direction": "顾沉视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "顾沉表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "顾沉双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "顾沉保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "顾沉头部只做与信息接收对应的轻微转动",
      "eye_direction": "顾沉视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "顾沉表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "顾沉双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "顾沉",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "顾沉",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "顾沉双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "林晚",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "顾沉",
      "body_action": "顾沉保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "顾沉双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "顾沉头部只做与信息接收对应的轻微转动",
      "eye_action": "顾沉视线先停留在当前关注点，再转向动作目标",
      "facial_action": "顾沉表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "林晚",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "顾沉",
      "body_action": "顾沉完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "林晚",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "顾沉",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "顾沉",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "林晚",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "顾沉",
      "detail": "顾沉双手保持在首帧确定的位置，手指动作小而清晰"
    },
    {
      "actor": "林晚",
      "detail": "顾沉双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "顾沉",
      "detail": "顾沉头部只做与信息接收对应的轻微转动"
    },
    {
      "actor": "林晚",
      "detail": "顾沉头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "顾沉",
      "detail": "顾沉视线先停留在当前关注点，再转向动作目标"
    },
    {
      "actor": "林晚",
      "detail": "顾沉视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "顾沉",
      "detail": "顾沉表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    },
    {
      "actor": "林晚",
      "detail": "顾沉表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "顾沉",
      "target": "林晚",
      "action": "顾沉指向红伞并向林晚解释"
    }
  ],
  "prop_interaction": [],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "继续静止保持"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "顾沉": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {},
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC001_005

```json
{
  "shot_id": "SH_E01_SC001_005",
  "duration": 5.0,
  "characters": [
    {
      "identity": "陆叔",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔上身向手提包靠近半步，林晚保持肩线不退，二人的距离只缩短一小段",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "陆叔低头看包后抬眼观察林晚，林晚头部延迟转向他",
      "eye_direction": "陆叔视线从包内硬物移到林晚眼睛，林晚短暂看向他的手",
      "facial_emotion": "陆叔嘴角的礼貌弧度消失，林晚下颌收紧但保持克制",
      "hand_pose": "林晚先松开提手，陆叔用右手接住包带，左手停在包口上方没有立即触碰",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔上身向手提包靠近半步，林晚保持肩线不退，二人的距离只缩短一小段",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "陆叔低头看包后抬眼观察林晚，林晚头部延迟转向他",
      "eye_direction": "陆叔视线从包内硬物移到林晚眼睛，林晚短暂看向他的手",
      "facial_emotion": "陆叔嘴角的礼貌弧度消失，林晚下颌收紧但保持克制",
      "hand_pose": "林晚先松开提手，陆叔用右手接住包带，左手停在包口上方没有立即触碰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [
    {
      "speaker": "陆叔",
      "text": "顾沉？你……你怎么在这儿？",
      "start_time": 0.6,
      "end_time": 2.8,
      "delivery": "低声、语速偏慢，关键词前有短暂停顿",
      "emotion": "从平静转为怀疑",
      "volume": "低",
      "pace": "slow",
      "pause_before": 0.2,
      "pause_after": 0.3,
      "reaction_target": "林晚"
    }
  ],
  "emotion_arc": [
    {
      "actor": "陆叔",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "陆叔",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚先松开提手，陆叔用右手接住包带，左手停在包口上方没有立即触碰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "林晚",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "陆叔",
      "body_action": "陆叔上身向手提包靠近半步，林晚保持肩线不退，二人的距离只缩短一小段",
      "hand_action": "林晚先松开提手，陆叔用右手接住包带，左手停在包口上方没有立即触碰",
      "head_action": "陆叔低头看包后抬眼观察林晚，林晚头部延迟转向他",
      "eye_action": "陆叔视线从包内硬物移到林晚眼睛，林晚短暂看向他的手",
      "facial_action": "陆叔嘴角的礼貌弧度消失，林晚下颌收紧但保持克制",
      "dialogue": "顾沉？你……你怎么在这儿？",
      "dialogue_delivery": "低声、慢速",
      "lip_sync_window": "0.8–1.8",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "林晚",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "陆叔",
      "body_action": "陆叔完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "顾沉？你……你怎么在这儿？",
      "dialogue_delivery": "关键词后保留短暂停顿",
      "lip_sync_window": "1.8–2.8",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "林晚",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "陆叔",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "陆叔",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "林晚",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "陆叔",
      "detail": "林晚先松开提手，陆叔用右手接住包带，左手停在包口上方没有立即触碰"
    },
    {
      "actor": "林晚",
      "detail": "林晚先松开提手，陆叔用右手接住包带，左手停在包口上方没有立即触碰"
    }
  ],
  "head_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔低头看包后抬眼观察林晚，林晚头部延迟转向他"
    },
    {
      "actor": "林晚",
      "detail": "陆叔低头看包后抬眼观察林晚，林晚头部延迟转向他"
    }
  ],
  "eye_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔视线从包内硬物移到林晚眼睛，林晚短暂看向他的手"
    },
    {
      "actor": "林晚",
      "detail": "陆叔视线从包内硬物移到林晚眼睛，林晚短暂看向他的手"
    }
  ],
  "facial_changes": [
    {
      "actor": "陆叔",
      "detail": "陆叔嘴角的礼貌弧度消失，林晚下颌收紧但保持克制"
    },
    {
      "actor": "林晚",
      "detail": "陆叔嘴角的礼貌弧度消失，林晚下颌收紧但保持克制"
    }
  ],
  "interaction_beats": [
    {
      "actor": "陆叔",
      "target": "林晚",
      "action": "陆叔接过手提包并发现硬物"
    }
  ],
  "prop_interaction": [
    {
      "prop": "HANDBAG",
      "state": "承载线索"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "跟拍"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "陆叔": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "手提包": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC001_006

```json
{
  "shot_id": "SH_E01_SC001_006",
  "duration": 5.0,
  "characters": [
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "林晚",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "林晚",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "当前线索",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "林晚",
      "body_action": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "林晚头部只做与信息接收对应的轻微转动",
      "eye_action": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_action": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "当前线索",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "林晚",
      "body_action": "林晚完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "当前线索",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "保持对线索的注视",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "林晚",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "林晚",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "当前线索",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "林晚",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "林晚",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "林晚",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "林晚",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "林晚",
      "target": "prop",
      "action": "林晚确认红伞消失只留下水痕"
    }
  ],
  "prop_interaction": [
    {
      "prop": "BROKEN_UMBRELLA_RIB",
      "state": "证据状态"
    },
    {
      "prop": "RED_UMBRELLA",
      "state": "关键视觉线索"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "继续静止保持"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "折断的红伞伞骨": "保持本镜最终状态",
      "红伞": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC001_007

```json
{
  "shot_id": "SH_E01_SC001_007",
  "duration": 5.0,
  "characters": [
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "陆叔",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "林晚",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "林晚",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "陆叔",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "林晚",
      "body_action": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "林晚头部只做与信息接收对应的轻微转动",
      "eye_action": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_action": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "陆叔",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "林晚",
      "body_action": "林晚完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "陆叔",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "陆叔",
      "body_action": "陆叔完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "林晚",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "林晚",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "陆叔",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "林晚",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    },
    {
      "actor": "陆叔",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "林晚",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    },
    {
      "actor": "陆叔",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "林晚",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    },
    {
      "actor": "陆叔",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "林晚",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    },
    {
      "actor": "陆叔",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "林晚",
      "target": "陆叔",
      "action": "林晚看向站台入口，陆叔示意返回"
    }
  ],
  "prop_interaction": [],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "横摇"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "陆叔": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {},
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC001_008

```json
{
  "shot_id": "SH_E01_SC001_008",
  "duration": 5.0,
  "characters": [
    {
      "identity": "顾沉",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "顾沉站在站台方向，林晚转身时脚步先停再离开，双方空间关系不改变",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "顾沉只向空站台轻微转头，林晚转身后不再回头",
      "eye_direction": "顾沉看向站台远处，林晚视线落在离开方向",
      "facial_emotion": "顾沉保持沉静，林晚的嘴角收紧并压住呼吸",
      "hand_pose": "林晚右手收拢靠近身体，顾沉的手臂保持垂落不追赶",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "顾沉站在站台方向，林晚转身时脚步先停再离开，双方空间关系不改变",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "顾沉只向空站台轻微转头，林晚转身后不再回头",
      "eye_direction": "顾沉看向站台远处，林晚视线落在离开方向",
      "facial_emotion": "顾沉保持沉静，林晚的嘴角收紧并压住呼吸",
      "hand_pose": "林晚右手收拢靠近身体，顾沉的手臂保持垂落不追赶",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [
    {
      "speaker": "顾沉",
      "text": "伞骨，断了，就该扔掉。留着，容易扎手。",
      "start_time": 0.6,
      "end_time": 2.8,
      "delivery": "低声、语速偏慢，关键词前有短暂停顿",
      "emotion": "从平静转为怀疑",
      "volume": "低",
      "pace": "slow",
      "pause_before": 0.2,
      "pause_after": 0.3,
      "reaction_target": "林晚"
    }
  ],
  "emotion_arc": [
    {
      "actor": "顾沉",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "顾沉",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚右手收拢靠近身体，顾沉的手臂保持垂落不追赶",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "林晚",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "顾沉",
      "body_action": "顾沉站在站台方向，林晚转身时脚步先停再离开，双方空间关系不改变",
      "hand_action": "林晚右手收拢靠近身体，顾沉的手臂保持垂落不追赶",
      "head_action": "顾沉只向空站台轻微转头，林晚转身后不再回头",
      "eye_action": "顾沉看向站台远处，林晚视线落在离开方向",
      "facial_action": "顾沉保持沉静，林晚的嘴角收紧并压住呼吸",
      "dialogue": "伞骨，断了，就该扔掉。留着，容易扎手。",
      "dialogue_delivery": "低声、慢速",
      "lip_sync_window": "0.8–1.8",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "林晚",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "顾沉",
      "body_action": "顾沉完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "伞骨，断了，就该扔掉。留着，容易扎手。",
      "dialogue_delivery": "关键词后保留短暂停顿",
      "lip_sync_window": "1.8–2.8",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "林晚",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "顾沉",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "顾沉",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "林晚",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "顾沉",
      "detail": "林晚右手收拢靠近身体，顾沉的手臂保持垂落不追赶"
    },
    {
      "actor": "林晚",
      "detail": "林晚右手收拢靠近身体，顾沉的手臂保持垂落不追赶"
    }
  ],
  "head_movement": [
    {
      "actor": "顾沉",
      "detail": "顾沉只向空站台轻微转头，林晚转身后不再回头"
    },
    {
      "actor": "林晚",
      "detail": "顾沉只向空站台轻微转头，林晚转身后不再回头"
    }
  ],
  "eye_movement": [
    {
      "actor": "顾沉",
      "detail": "顾沉看向站台远处，林晚视线落在离开方向"
    },
    {
      "actor": "林晚",
      "detail": "顾沉看向站台远处，林晚视线落在离开方向"
    }
  ],
  "facial_changes": [
    {
      "actor": "顾沉",
      "detail": "顾沉保持沉静，林晚的嘴角收紧并压住呼吸"
    },
    {
      "actor": "林晚",
      "detail": "顾沉保持沉静，林晚的嘴角收紧并压住呼吸"
    }
  ],
  "interaction_beats": [
    {
      "actor": "顾沉",
      "target": "林晚",
      "action": "顾沉望向空荡站台，林晚转身离开"
    }
  ],
  "prop_interaction": [],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "缓慢推近"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "顾沉": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {},
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC002_001

```json
{
  "shot_id": "SH_E01_SC002_001",
  "duration": 5.0,
  "characters": [
    {
      "identity": "陆叔",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "陆叔头部只做与信息接收对应的轻微转动",
      "eye_direction": "陆叔视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "陆叔双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "陆叔头部只做与信息接收对应的轻微转动",
      "eye_direction": "陆叔视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "陆叔双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "陆叔",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "陆叔",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "陆叔双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "林晚",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "陆叔",
      "body_action": "陆叔保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "陆叔双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "陆叔头部只做与信息接收对应的轻微转动",
      "eye_action": "陆叔视线先停留在当前关注点，再转向动作目标",
      "facial_action": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "林晚",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "陆叔",
      "body_action": "陆叔完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "林晚",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "陆叔",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "陆叔",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "林晚",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔双手保持在首帧确定的位置，手指动作小而清晰"
    },
    {
      "actor": "林晚",
      "detail": "陆叔双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔头部只做与信息接收对应的轻微转动"
    },
    {
      "actor": "林晚",
      "detail": "陆叔头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔视线先停留在当前关注点，再转向动作目标"
    },
    {
      "actor": "林晚",
      "detail": "陆叔视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "陆叔",
      "detail": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    },
    {
      "actor": "林晚",
      "detail": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "陆叔",
      "target": "林晚",
      "action": "陆叔清洗手，林晚走近餐桌"
    }
  ],
  "prop_interaction": [
    {
      "prop": "APPLE",
      "state": "生活道具"
    },
    {
      "prop": "DOOR_LOCK",
      "state": "出口连续性标记"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "继续静止保持"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "陆叔": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "苹果": "保持本镜最终状态",
      "门锁": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC002_002

```json
{
  "shot_id": "SH_E01_SC002_002",
  "duration": 5.0,
  "characters": [
    {
      "identity": "陆叔",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔坐在桌边保持躯干稳定，林晚身体略前倾但双脚不动",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "对白开始前陆叔抬头，林晚在听到关键词后轻微侧头",
      "eye_direction": "陆叔先看桌面再看林晚，林晚始终盯住陆叔的眼睛",
      "facial_emotion": "陆叔表情平和但眼神变冷，林晚眉间收紧、嘴唇短暂抿住",
      "hand_pose": "陆叔手指缓慢绕过杯沿后停住，林晚双手压住手提包边缘",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔坐在桌边保持躯干稳定，林晚身体略前倾但双脚不动",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "对白开始前陆叔抬头，林晚在听到关键词后轻微侧头",
      "eye_direction": "陆叔先看桌面再看林晚，林晚始终盯住陆叔的眼睛",
      "facial_emotion": "陆叔表情平和但眼神变冷，林晚眉间收紧、嘴唇短暂抿住",
      "hand_pose": "陆叔手指缓慢绕过杯沿后停住，林晚双手压住手提包边缘",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [
    {
      "speaker": "陆叔",
      "text": "陆叔：晚晚，你看看你，跑那么快做什么？在车站吓我一跳。脸色这么差，是不是又没好好吃饭？来，先坐下，陆叔给你洗个苹果。",
      "start_time": 0.6,
      "end_time": 2.8,
      "delivery": "低声、语速偏慢，关键词前有短暂停顿",
      "emotion": "从平静转为怀疑",
      "volume": "低",
      "pace": "slow",
      "pause_before": 0.2,
      "pause_after": 0.3,
      "reaction_target": "林晚"
    }
  ],
  "emotion_arc": [
    {
      "actor": "陆叔",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "陆叔",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "陆叔手指缓慢绕过杯沿后停住，林晚双手压住手提包边缘",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "林晚",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "陆叔",
      "body_action": "陆叔坐在桌边保持躯干稳定，林晚身体略前倾但双脚不动",
      "hand_action": "陆叔手指缓慢绕过杯沿后停住，林晚双手压住手提包边缘",
      "head_action": "对白开始前陆叔抬头，林晚在听到关键词后轻微侧头",
      "eye_action": "陆叔先看桌面再看林晚，林晚始终盯住陆叔的眼睛",
      "facial_action": "陆叔表情平和但眼神变冷，林晚眉间收紧、嘴唇短暂抿住",
      "dialogue": "陆叔：晚晚，你看看你，跑那么快做什么？在车站吓我一跳。脸色这么差，是不是又没好好吃饭？来，先坐下，陆叔给你洗个苹果。",
      "dialogue_delivery": "低声、慢速",
      "lip_sync_window": "0.8–1.8",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "林晚",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "陆叔",
      "body_action": "陆叔完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "陆叔：晚晚，你看看你，跑那么快做什么？在车站吓我一跳。脸色这么差，是不是又没好好吃饭？来，先坐下，陆叔给你洗个苹果。",
      "dialogue_delivery": "关键词后保留短暂停顿",
      "lip_sync_window": "1.8–2.8",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "林晚",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "陆叔",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "陆叔",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "林晚",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔手指缓慢绕过杯沿后停住，林晚双手压住手提包边缘"
    },
    {
      "actor": "林晚",
      "detail": "陆叔手指缓慢绕过杯沿后停住，林晚双手压住手提包边缘"
    }
  ],
  "head_movement": [
    {
      "actor": "陆叔",
      "detail": "对白开始前陆叔抬头，林晚在听到关键词后轻微侧头"
    },
    {
      "actor": "林晚",
      "detail": "对白开始前陆叔抬头，林晚在听到关键词后轻微侧头"
    }
  ],
  "eye_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔先看桌面再看林晚，林晚始终盯住陆叔的眼睛"
    },
    {
      "actor": "林晚",
      "detail": "陆叔先看桌面再看林晚，林晚始终盯住陆叔的眼睛"
    }
  ],
  "facial_changes": [
    {
      "actor": "陆叔",
      "detail": "陆叔表情平和但眼神变冷，林晚眉间收紧、嘴唇短暂抿住"
    },
    {
      "actor": "林晚",
      "detail": "陆叔表情平和但眼神变冷，林晚眉间收紧、嘴唇短暂抿住"
    }
  ],
  "interaction_beats": [
    {
      "actor": "陆叔",
      "target": "林晚",
      "action": "陆叔重复一段话，林晚在对面听着"
    }
  ],
  "prop_interaction": [],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "继续静止保持"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "陆叔": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {},
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC002_003

```json
{
  "shot_id": "SH_E01_SC002_003",
  "duration": 5.0,
  "characters": [
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "林晚",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "林晚",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "当前线索",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "林晚",
      "body_action": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "林晚头部只做与信息接收对应的轻微转动",
      "eye_action": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_action": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "当前线索",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "林晚",
      "body_action": "林晚完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "当前线索",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "保持对线索的注视",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "林晚",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "林晚",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "当前线索",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "林晚",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "林晚",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "林晚",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "林晚",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "林晚",
      "target": "prop",
      "action": "林晚寻找可以证明记忆的线索"
    }
  ],
  "prop_interaction": [
    {
      "prop": "HANDBAG",
      "state": "承载线索"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "继续静止保持"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "手提包": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC002_004

```json
{
  "shot_id": "SH_E01_SC002_004",
  "duration": 5.0,
  "characters": [
    {
      "identity": "陆叔",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "陆叔头部只做与信息接收对应的轻微转动",
      "eye_direction": "陆叔视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "陆叔双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "陆叔头部只做与信息接收对应的轻微转动",
      "eye_direction": "陆叔视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "陆叔双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "陆叔",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "陆叔",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "陆叔双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "林晚",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "陆叔",
      "body_action": "陆叔保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "陆叔双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "陆叔头部只做与信息接收对应的轻微转动",
      "eye_action": "陆叔视线先停留在当前关注点，再转向动作目标",
      "facial_action": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "林晚",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "陆叔",
      "body_action": "陆叔完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "林晚",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "陆叔",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "陆叔",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "林晚",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔双手保持在首帧确定的位置，手指动作小而清晰"
    },
    {
      "actor": "林晚",
      "detail": "陆叔双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔头部只做与信息接收对应的轻微转动"
    },
    {
      "actor": "林晚",
      "detail": "陆叔头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔视线先停留在当前关注点，再转向动作目标"
    },
    {
      "actor": "林晚",
      "detail": "陆叔视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "陆叔",
      "detail": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    },
    {
      "actor": "林晚",
      "detail": "陆叔表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "陆叔",
      "target": "林晚",
      "action": "陆叔发现桌面硬物并看向林晚"
    }
  ],
  "prop_interaction": [
    {
      "prop": "POCKET_HARD_OBJECT",
      "state": "未完全显露的线索"
    },
    {
      "prop": "TABLE_SCRATCH",
      "state": "记忆线索"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "轻微重新构图"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "陆叔": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "口袋里的硬物": "保持本镜最终状态",
      "桌面划痕": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC002_005

```json
{
  "shot_id": "SH_E01_SC002_005",
  "duration": 5.0,
  "characters": [
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚头部只做与信息接收对应的轻微转动",
      "eye_direction": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_emotion": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "hand_pose": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "林晚",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "林晚",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "当前线索",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "林晚",
      "body_action": "林晚保持与首帧一致的站位，肩线和重心可被连续追踪",
      "hand_action": "林晚双手保持在首帧确定的位置，手指动作小而清晰",
      "head_action": "林晚头部只做与信息接收对应的轻微转动",
      "eye_action": "林晚视线先停留在当前关注点，再转向动作目标",
      "facial_action": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "当前线索",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "疑惑",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "林晚",
      "body_action": "林晚完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "当前线索",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "保持对线索的注视",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "林晚",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "林晚",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "当前线索",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "林晚",
      "detail": "林晚双手保持在首帧确定的位置，手指动作小而清晰"
    }
  ],
  "head_movement": [
    {
      "actor": "林晚",
      "detail": "林晚头部只做与信息接收对应的轻微转动"
    }
  ],
  "eye_movement": [
    {
      "actor": "林晚",
      "detail": "林晚视线先停留在当前关注点，再转向动作目标"
    }
  ],
  "facial_changes": [
    {
      "actor": "林晚",
      "detail": "林晚表情从平静转为克制的警觉，变化通过眉间和嘴角体现"
    }
  ],
  "interaction_beats": [
    {
      "actor": "林晚",
      "target": "prop",
      "action": "林晚取出红色纤维确认"
    }
  ],
  "prop_interaction": [
    {
      "prop": "RED_FIBER",
      "state": "证据状态"
    }
  ],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "继续静止保持"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {
      "红色纤维": "保持本镜最终状态"
    },
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC002_006

```json
{
  "shot_id": "SH_E01_SC002_006",
  "duration": 5.0,
  "characters": [
    {
      "identity": "陆叔",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔坐姿不变，只有上身向前压入暖光，林晚保持在门边的退让距离",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "陆叔抬下巴看向林晚，林晚头部微向后收",
      "eye_direction": "陆叔视线锁定林晚，林晚短暂避开后重新看回",
      "facial_emotion": "陆叔的笑意只停留在嘴角，眼神没有笑；林晚呼吸变浅",
      "hand_pose": "陆叔指尖轻敲桌面两次后停止，林晚手指抓紧包带",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "陆叔坐姿不变，只有上身向前压入暖光，林晚保持在门边的退让距离",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "陆叔抬下巴看向林晚，林晚头部微向后收",
      "eye_direction": "陆叔视线锁定林晚，林晚短暂避开后重新看回",
      "facial_emotion": "陆叔的笑意只停留在嘴角，眼神没有笑；林晚呼吸变浅",
      "hand_pose": "陆叔指尖轻敲桌面两次后停止，林晚手指抓紧包带",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [
    {
      "speaker": "陆叔",
      "text": "陆叔：伞？你哪来的伞？你不是一直不喜欢带伞吗？嫌麻烦。来，吃苹果。",
      "start_time": 0.6,
      "end_time": 2.8,
      "delivery": "低声、语速偏慢，关键词前有短暂停顿",
      "emotion": "从平静转为怀疑",
      "volume": "低",
      "pace": "slow",
      "pause_before": 0.2,
      "pause_after": 0.3,
      "reaction_target": "林晚"
    }
  ],
  "emotion_arc": [
    {
      "actor": "陆叔",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "陆叔",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "陆叔指尖轻敲桌面两次后停止，林晚手指抓紧包带",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "林晚",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "陆叔",
      "body_action": "陆叔坐姿不变，只有上身向前压入暖光，林晚保持在门边的退让距离",
      "hand_action": "陆叔指尖轻敲桌面两次后停止，林晚手指抓紧包带",
      "head_action": "陆叔抬下巴看向林晚，林晚头部微向后收",
      "eye_action": "陆叔视线锁定林晚，林晚短暂避开后重新看回",
      "facial_action": "陆叔的笑意只停留在嘴角，眼神没有笑；林晚呼吸变浅",
      "dialogue": "陆叔：伞？你哪来的伞？你不是一直不喜欢带伞吗？嫌麻烦。来，吃苹果。",
      "dialogue_delivery": "低声、慢速",
      "lip_sync_window": "0.8–1.8",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "林晚",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "警觉",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "陆叔",
      "body_action": "陆叔完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "陆叔：伞？你哪来的伞？你不是一直不喜欢带伞吗？嫌麻烦。来，吃苹果。",
      "dialogue_delivery": "关键词后保留短暂停顿",
      "lip_sync_window": "1.8–2.8",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "林晚",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "林晚",
      "body_action": "林晚完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "陆叔",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "陆叔",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "林晚",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔指尖轻敲桌面两次后停止，林晚手指抓紧包带"
    },
    {
      "actor": "林晚",
      "detail": "陆叔指尖轻敲桌面两次后停止，林晚手指抓紧包带"
    }
  ],
  "head_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔抬下巴看向林晚，林晚头部微向后收"
    },
    {
      "actor": "林晚",
      "detail": "陆叔抬下巴看向林晚，林晚头部微向后收"
    }
  ],
  "eye_movement": [
    {
      "actor": "陆叔",
      "detail": "陆叔视线锁定林晚，林晚短暂避开后重新看回"
    },
    {
      "actor": "林晚",
      "detail": "陆叔视线锁定林晚，林晚短暂避开后重新看回"
    }
  ],
  "facial_changes": [
    {
      "actor": "陆叔",
      "detail": "陆叔的笑意只停留在嘴角，眼神没有笑；林晚呼吸变浅"
    },
    {
      "actor": "林晚",
      "detail": "陆叔的笑意只停留在嘴角，眼神没有笑；林晚呼吸变浅"
    }
  ],
  "interaction_beats": [
    {
      "actor": "陆叔",
      "target": "林晚",
      "action": "陆叔露出笑意形成无声威胁"
    }
  ],
  "prop_interaction": [],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "缓慢推近"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "陆叔": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {},
    "camera_framing": "current framing"
  }
}
```
## SH_E01_SC002_007

```json
{
  "shot_id": "SH_E01_SC002_007",
  "duration": 5.0,
  "characters": [
    {
      "identity": "林晚",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "镜头沿门口方向缓慢推进，林晚后退一步后停住，陆叔留在餐桌旁",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚回头确认出口再看向陆叔，陆叔保持正面",
      "eye_direction": "林晚视线在门锁与陆叔之间切换一次，最后停在陆叔",
      "facial_emotion": "林晚从压抑疑惑转为明确警觉，陆叔维持难以判断的平静",
      "hand_pose": "林晚左手扶住门边，右手护住手提包，陆叔双手留在身体两侧",
      "body_balance": "重心稳定，避免无授权位移"
    },
    {
      "identity": "陆叔",
      "costume": "沿用锁定人物资产与本镜服装变体",
      "body_pose": "镜头沿门口方向缓慢推进，林晚后退一步后停住，陆叔留在餐桌旁",
      "torso_direction": "朝向当前互动目标",
      "head_direction": "林晚回头确认出口再看向陆叔，陆叔保持正面",
      "eye_direction": "林晚视线在门锁与陆叔之间切换一次，最后停在陆叔",
      "facial_emotion": "林晚从压抑疑惑转为明确警觉，陆叔维持难以判断的平静",
      "hand_pose": "林晚左手扶住门边，右手护住手提包，陆叔双手留在身体两侧",
      "body_balance": "重心稳定，避免无授权位移"
    }
  ],
  "dialogue": [],
  "emotion_arc": [
    {
      "actor": "林晚",
      "emotion_start": "平静或疑惑",
      "trigger": "当前镜头信息落点",
      "transition": "注意力集中→判断→克制警觉",
      "emotion_end": "克制警觉"
    }
  ],
  "body_movement": [
    {
      "start_time": 0.0,
      "end_time": 0.8,
      "actor": "林晚",
      "body_action": "保持首帧姿态，呼吸连续",
      "hand_action": "林晚左手扶住门边，右手护住手提包，陆叔双手留在身体两侧",
      "head_action": "保持首帧头部方向",
      "eye_action": "视线停留在起始关注点",
      "facial_action": "表情保持起始状态",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态保持不变",
      "interaction_target": "陆叔",
      "camera_action": "静止或保持起始构图",
      "emotion_start": "平静",
      "emotion_end": "注意力集中",
      "ending_state": "首帧姿态连续"
    },
    {
      "start_time": 0.8,
      "end_time": 1.8,
      "actor": "林晚",
      "body_action": "镜头沿门口方向缓慢推进，林晚后退一步后停住，陆叔留在餐桌旁",
      "hand_action": "林晚左手扶住门边，右手护住手提包，陆叔双手留在身体两侧",
      "head_action": "林晚回头确认出口再看向陆叔，陆叔保持正面",
      "eye_action": "林晚视线在门锁与陆叔之间切换一次，最后停在陆叔",
      "facial_action": "林晚从压抑疑惑转为明确警觉，陆叔维持难以判断的平静",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具只发生与剧情证据相关的微小变化",
      "interaction_target": "陆叔",
      "camera_action": "保持或开始轻微重新构图",
      "emotion_start": "注意力集中",
      "emotion_end": "警觉",
      "ending_state": "主体完成第一阶段动作"
    },
    {
      "start_time": 1.8,
      "end_time": 3.0,
      "actor": "林晚",
      "body_action": "林晚完成主要身体动作并在动作末端停住",
      "hand_action": "手部完成一次明确的抓取、放置或停顿，不重复动作",
      "head_action": "头部跟随视线完成一次小幅调整",
      "eye_action": "视线锁定交互目标",
      "facial_action": "眉间和嘴角完成可见的情绪转折",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "关键道具保持可见并与人物手部关系连续",
      "interaction_target": "陆叔",
      "camera_action": "只执行一项已授权的镜头运动",
      "emotion_start": "疑惑",
      "emotion_end": "警觉",
      "ending_state": "主要动作完成，空间关系不变"
    },
    {
      "start_time": 3.0,
      "end_time": 4.2,
      "actor": "陆叔",
      "body_action": "陆叔完成一次可见反应并停住",
      "hand_action": "反应角色手部动作短促后回到稳定位置",
      "head_action": "反应角色头部向主要动作目标转动",
      "eye_action": "先避开再重新看向互动对象",
      "facial_action": "嘴角或眉间出现轻微收紧",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具状态不被无授权改变",
      "interaction_target": "林晚",
      "camera_action": "运动减速并准备停止",
      "emotion_start": "观察",
      "emotion_end": "克制反应",
      "ending_state": "反应完成并回到可衔接姿态"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "actor": "林晚",
      "body_action": "所有身体动作停止，呼吸保持轻微可见",
      "hand_action": "手部停在最终位置，手指不再继续动作",
      "head_action": "头部保持最终方向",
      "eye_action": "视线固定在下一镜可继承的目标",
      "facial_action": "最终情绪稳定在克制警觉",
      "dialogue": "N/A",
      "dialogue_delivery": "N/A",
      "lip_sync_window": "N/A",
      "prop_action": "道具进入最终状态",
      "interaction_target": "陆叔",
      "camera_action": "镜头停止并保持",
      "emotion_start": "克制反应",
      "emotion_end": "克制警觉",
      "ending_state": "位置、姿态、视线、情绪和道具状态冻结"
    }
  ],
  "hand_movement": [
    {
      "actor": "林晚",
      "detail": "林晚左手扶住门边，右手护住手提包，陆叔双手留在身体两侧"
    },
    {
      "actor": "陆叔",
      "detail": "林晚左手扶住门边，右手护住手提包，陆叔双手留在身体两侧"
    }
  ],
  "head_movement": [
    {
      "actor": "林晚",
      "detail": "林晚回头确认出口再看向陆叔，陆叔保持正面"
    },
    {
      "actor": "陆叔",
      "detail": "林晚回头确认出口再看向陆叔，陆叔保持正面"
    }
  ],
  "eye_movement": [
    {
      "actor": "林晚",
      "detail": "林晚视线在门锁与陆叔之间切换一次，最后停在陆叔"
    },
    {
      "actor": "陆叔",
      "detail": "林晚视线在门锁与陆叔之间切换一次，最后停在陆叔"
    }
  ],
  "facial_changes": [
    {
      "actor": "林晚",
      "detail": "林晚从压抑疑惑转为明确警觉，陆叔维持难以判断的平静"
    },
    {
      "actor": "陆叔",
      "detail": "林晚从压抑疑惑转为明确警觉，陆叔维持难以判断的平静"
    }
  ],
  "interaction_beats": [
    {
      "actor": "林晚",
      "target": "陆叔",
      "action": "林晚后退到门边，陆叔停在昏暗灯光中"
    }
  ],
  "prop_interaction": [],
  "camera_movement": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "action": "静止保持"
    },
    {
      "start_time": 2.0,
      "end_time": 4.2,
      "action": "轻微环绕"
    },
    {
      "start_time": 4.2,
      "end_time": 5.0,
      "action": "停止并保持"
    }
  ],
  "ending_pose": {
    "characters": {
      "林晚": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      },
      "陆叔": {
        "position": "保持本镜空间区位",
        "pose": "完成动作后稳定",
        "head_direction": "最终头部方向",
        "eye_direction": "最终视线目标",
        "emotion": "克制警觉",
        "costume": "保持锁定变体"
      }
    },
    "props": {},
    "camera_framing": "current framing"
  }
}
```
