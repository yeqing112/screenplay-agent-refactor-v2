# Episode 1 SceneBlocking V2（Phase B）

> 这里只描述人物、道具、空间和互动发生方式；不包含 shot size、lens、camera movement、duration 或 edit cut。

## E01_SC001｜旧火车站售票厅

### 空间概览
- geometry_precision：RELATIVE
- 空间逻辑：relative positions are authoritative within the locked location; no camera decision is encoded

### Zone
- `ST_TICKET` 售票窗口：大厅一侧固定锚点；关键道具：车票
- `ST_CENTER` 售票大厅中央：售票窗与检票口之间；关键道具：手提包
- `ST_PLATFORM_SIGHT` 站台视觉区域：从大厅可见的远侧；关键道具：红伞
- `ST_CHECK` 检票口方向：林晚原计划离开的连接方向；关键道具：无
- `ST_REAR` 大厅后侧来人方向：顾沉和陆叔进入的相对方向；关键道具：无

### 人物初始位置 / 移动 / Entry / Exit
- **林晚**：entry=already_present_at_ST_TICKET；初始=ST_TICKET；面向=售票窗口_then_ST_PLATFORM_SIGHT；exit=以回家为借口向ST_CHECK后退
  - `SC01-B03` ST_TICKET → ST_CENTER：红伞吸引注意
  - `SC01-B10` ST_CENTER → ST_CHECK：准备离开后停住调查
- **顾沉**：entry=从ST_REAR进入；初始=ST_REAR；面向=林晚与手提包；exit=从ST_CENTER向人群方向离开
  - `SC01-B05` ST_REAR → ST_CENTER：接近并提问
- **陆叔**：entry=从ST_REAR进入；初始=ST_REAR；面向=林晚；exit=与林晚一起朝ST_CHECK返回
  - `SC01-B07` ST_REAR → ST_CENTER：接过手提包并挡住林晚与出口的直线
- **售票员**：entry=already_present_at_ST_TICKET；初始=ST_TICKET；面向=林晚；exit=remains_at_ST_TICKET

### Beat Blocking
- `SC01-B03`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B03`
- `SC01-B04`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B04`
- `SC01-B05`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B05`
- `SC01-B06`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B06`
- `SC01-B08`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B08`
- `SC01-B09`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B09`
- `SC01-B10`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B10`
- `SC01-B11`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B11`
- `SC01-B12`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B12`
- `SC01-B13`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC01-B13`

### Eyeline
- `SC01-B03`：林晚 → RED_UMBRELLA（SCRIPT_ACTION）
- `SC01-B04`：顾沉 → HANDBAG（SCRIPT_ACTION）
- `SC01-B06`：顾沉 → RED_UMBRELLA（DIRECTOR_AUTHORING_DECISION）
- `SC01-B08`：林晚 → 陆叔（DIRECTOR_AUTHORING_DECISION）
- `SC01-B10`：林晚 → HANDBAG（SCRIPT_ACTION）

### 关键道具状态
- `SC01-B03` `RED_UMBRELLA`：visible @ ST_PLATFORM_SIGHT
- `SC01-B09` `RED_UMBRELLA`：absent; water_trace_remains @ ST_PLATFORM_SIGHT
- `SC01-B04` `BROKEN_UMBRELLA_RIB`：visible_inside_bag @ HANDBAG
- `SC01-B10` `BROKEN_UMBRELLA_RIB`：missing @ HANDBAG
- `SC01-B07` `HANDBAG`：transferred_to_LU_SHU @ ST_CENTER
- `SC01-B01` `TICKET`：held_by_LIN_WAN @ ST_TICKET

### Interaction
- `SC01-B05` 顾沉 → 林晚：approaches_and_questions；空间结果：缩短距离但保留林晚退向检票口的可能
- `SC01-B07` 陆叔 → HANDBAG：takes_bag；空间结果：陆叔获得道具控制权并介入林晚出口方向
- `SC01-B12` 陆叔 → 林晚：agrees_too_quickly_to_return；空间结果：两人共同转向ST_CHECK

### Axis constraints
- `AXIS_LW_GC`：林晚 ↔ 顾沉，从 `SC01-B05` 建立；PRESERVE_UNLESS_MOTIVATED_CROSS
- `AXIS_LW_LS`：林晚 ↔ 陆叔，从 `SC01-B07` 建立；PRESERVE_UNLESS_MOTIVATED_CROSS

### 空间戏剧逻辑
人物移动持续改变出口、道具控制权和互相可见关系；所有状态都绑定到 ScriptIR DramaticBeat。

## E01_SC002｜林晚的公寓客厅

### 空间概览
- geometry_precision：RELATIVE
- 空间逻辑：relative positions are authoritative within the locked location; no camera decision is encoded

### Zone
- `APT_ENTRY` 玄关/门：林晚进出和可见出口；关键道具：门锁, 水渍, 暗红纤维
- `APT_CENTER` 客厅中央：门、厨房、茶几之间的初始缓冲区；关键道具：手提包
- `APT_KITCHEN` 厨房/水槽：陆叔可用日常动作介入客厅；关键道具：苹果, 水槽
- `APT_TABLE` 茶几：林晚后退时的物证和身体边界；关键道具：茶几划痕
- `APT_WINDOW` 窗户：侧向光线和纤维飘落可见区域；关键道具：暗红纤维

### 人物初始位置 / 移动 / Entry / Exit
- **林晚**：entry=从APT_ENTRY进入；初始=APT_CENTER靠近门的内侧；面向=陆叔_then_环境物证；exit=remains_trapped_at_APT_TABLE
  - `SC02-B02` APT_CENTER → APT_CENTER靠近陆叔：主动试探
  - `SC02-B04` APT_CENTER → APT_TABLE侧边：被Gaslighting后寻找物证
  - `SC02-B07` APT_TABLE侧边 → APT_TABLE后缘：面对威胁后退
- **陆叔**：entry=随林晚从APT_ENTRY进入并锁门；初始=APT_ENTRY与APT_CENTER之间；面向=林晚；exit=remains_between_LIN_WAN_and_APT_ENTRY
  - `SC02-B01` APT_ENTRY → APT_KITCHEN：用洗苹果建立照顾日常
  - `SC02-B03` APT_KITCHEN → APT_CENTER与APT_ENTRY之间：D029后介入出口关系
  - `SC02-B07` APT_CENTER → APT_TABLE前方：威胁显形并压缩距离

### Beat Blocking
- `SC02-B02`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC02-B02`
- `SC02-B03`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC02-B03`
- `SC02-B04`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC02-B04`
- `SC02-B05`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC02-B05`
- `SC02-B06`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC02-B06`
- `SC02-B07`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC02-B07`
- `SC02-B08`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC02-B08`
- `SC02-B09`：NO_POSITION_CHANGE unless a movement is declared；导演绑定 `SC02-B09`

### Eyeline
- `SC02-B02`：林晚 → 陆叔（DIRECTOR_AUTHORING_DECISION）
- `SC02-B03`：陆叔 → 林晚（DIRECTOR_AUTHORING_DECISION）
- `SC02-B05`：林晚 → TABLE_SCRATCH（SCRIPT_ACTION）
- `SC02-B05`：林晚 → POCKET_HARD_OBJECT（SCRIPT_ACTION）
- `SC02-B06`：林晚 → RED_FIBER（SCRIPT_ACTION）
- `SC02-B09`：陆叔 → RED_FIBER（SCRIPT_ACTION）

### 关键道具状态
- `SC02-B01` `DOOR_LOCK`：locked_by_LU_SHU @ APT_ENTRY
- `SC02-B01` `APPLE`：washed_by_LU_SHU @ APT_KITCHEN
- `SC02-B05` `TABLE_SCRATCH`：visible_to_LIN_WAN @ APT_TABLE
- `SC02-B05` `POCKET_HARD_OBJECT`：in_LU_SHU_pocket @ APT_CENTER
- `SC02-B06` `RED_FIBER`：visible_on_water_trace @ APT_ENTRY
- `SC02-B04` `HANDBAG`：with_LIN_WAN @ APT_CENTER

### Interaction
- `SC02-B01` 陆叔 → DOOR_LOCK：locks_door；空间结果：出口从可用变成被陆叔控制
- `SC02-B03` 陆叔 → 林晚：gaslights_memory；空间结果：林晚停止向前并转向环境
- `SC02-B07` 陆叔 → 林晚：threatens；空间结果：陆叔站到林晚与门之间

### Axis constraints
- `AXIS_LW_LS_APT`：林晚 ↔ 陆叔，从 `SC02-B02` 建立；PRESERVE_UNLESS_MOTIVATED_CROSS

### 空间戏剧逻辑
人物移动持续改变出口、道具控制权和互相可见关系；所有状态都绑定到 ScriptIR DramaticBeat。
