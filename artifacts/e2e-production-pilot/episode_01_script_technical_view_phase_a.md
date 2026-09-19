# 红伞倒影（技术视图）

## E01_SC001  旧火车站售票厅

- `SC01-B01` [ACTION] importance=normal requires_reaction=False
    林晚站在售票窗前，额角有汗，攥紧旧皮包。
    objective=买票逃离
- `SC01-B02` [ACTION] importance=normal requires_reaction=False
    林晚要两张去南城的票，最早一班。
    objective=买票逃离
- `SC01-B03` [REVEAL] importance=critical requires_reaction=True
    林晚看见站台立柱旁一把收起的红色雨伞。
    objective=红伞第一次出现必须形成强视觉注意点
    info_delta=红伞出现
- `SC01-B04` [REVEAL] importance=critical requires_reaction=True
    林晚的手提包掉落，露出断裂的暗红色伞骨。
    objective=展示林晚拥有断伞骨
    info_delta=林晚拥有断伞骨
- `SC01-B05` [QUESTION] importance=normal requires_reaction=True
    顾沉突然出现，叫出林晚的名字。
    objective=引入威胁感来源
- `SC01-B06` [REVEAL] importance=critical requires_reaction=True
    顾沉说那把伞挺眼熟，伞骨断过、修补过但没修好。
    objective=顾沉知道得过多，危险感来源于此
    info_delta=顾沉知道伞骨
- `SC01-B07` [ACTION] importance=normal requires_reaction=False
    陆叔提着网兜出现，热心招呼林晚，接过她的手提包。
    objective=引入陆叔作为长辈伪装
- `SC01-B08` [REVEAL] importance=critical requires_reaction=True
    陆叔对红伞的追问反应异常，外套口袋鼓出长条状硬物。
    objective=把怀疑从顾沉引向陆叔
    info_delta=陆叔对红伞异常
- `SC01-B09` [REVEAL] importance=critical requires_reaction=True
    站台立柱旁的红伞不见了，只留下一小片深色水渍。
    objective=确认异常并非幻觉
    info_delta=红伞消失
- `SC01-B10` [DECISION] importance=critical requires_reaction=True
    林晚发现包扣被重新动过，断伞骨不见了。
    objective=推动她放弃登车
    info_delta=断伞骨丢失
- `SC01-B11` [DECISION] importance=critical requires_reaction=True
    林晚决定不上车，对陆叔说忘了拿一样东西，先回去。
    objective=林晚采取主动试探策略
    info_delta=林晚放弃登车
- `SC01-B12` [REACTION] importance=critical requires_reaction=True
    陆叔没有劝她登车，反而立刻同意回去。
    objective=陆叔过快同意本身成为新的怀疑节拍
- `SC01-B13` [ESCALATION] importance=critical requires_reaction=True
    顾沉低声说伞骨断了就该扔掉，容易扎手，然后走进人群消失。
    objective=强化谜样威胁并留下警示
    info_delta=顾沉留下双关警告
- `D001` **林晚** [OBJECTIVE_FACT] contradicts=[] notice=False
    两张去南城的票。最早一班。
- `D002` **售票员** [OBJECTIVE_FACT] contradicts=[] notice=False
    最近一班，十点十五。硬座还是卧铺？
- `D003` **林晚** [OBJECTIVE_FACT] contradicts=[] notice=False
    卧铺……下铺。
- `D004` **顾沉** [OBJECTIVE_FACT] contradicts=[] notice=False
    林晚。
- `D005` **林晚** [UNCERTAIN_CLAIM] contradicts=[] notice=False
    顾沉？你……你怎么在这儿？
- `D006` **顾沉** [OBJECTIVE_FACT] contradicts=[] notice=False
    路过。看到你，打个招呼。
- `D007` **顾沉** [CHARACTER_BELIEF] contradicts=[] notice=False
    要出门？南城？
- `D008` **林晚** [CHARACTER_BELIEF] contradicts=[] notice=False
    嗯，办点事。
- `D009` **顾沉** [OBJECTIVE_FACT] contradicts=[] notice=True
    那把伞，挺眼熟的。红色。伞骨好像断过。修补过，但没修好。
- `D010` **林晚** [CHARACTER_BELIEF] contradicts=[] notice=False
    什么伞？我不……
- `D011` **陆叔** [OBJECTIVE_FACT] contradicts=[] notice=False
    小晚！可算找到你了！你陆婶非让我给你塞这点路上吃的，说南城那边水果贵……
- `D012` **林晚** [OBJECTIVE_FACT] contradicts=[] notice=False
    ……朋友。顾沉。
- `D013` **陆叔** [OBJECTIVE_FACT] contradicts=[] notice=False
    红伞？没注意。下雨了？这天儿，是该带伞。
- `D014` **林晚** [QUESTION] contradicts=[] notice=False
    陆叔，你的伞呢？
- `D015` **陆叔** [OBJECTIVE_FACT] contradicts=[] notice=False
    没带啊。这不下雨，带啥伞。你这孩子，问东问西的。
- `D016` **陆叔** [OBJECTIVE_FACT] contradicts=[] notice=False
    走吧，小晚，检票了。
- `D017` **林晚** [CHARACTER_BELIEF] contradicts=[] notice=False
    我忘了拿一样东西。先回去。
- `D018` **陆叔** [OBJECTIVE_FACT] contradicts=[] notice=True
    好，那回去吧，我送你。
- `D019` **顾沉** [OBJECTIVE_FACT] contradicts=[] notice=True
    伞骨，断了，就该扔掉。留着，容易扎手。

## E01_SC002  林晚的公寓客厅

- `SC02-B01` [ACTION] importance=normal requires_reaction=False
    陆叔跟着林晚进公寓，反手把门锁旋了两圈。
    objective=建立密闭空间与不安
- `SC02-B02` [QUESTION] importance=critical requires_reaction=True
    林晚问陆叔是不是早上很早就去过车站。
    objective=林晚开始主动试探
- `SC02-B03` [REVEAL] importance=critical requires_reaction=True
    陆叔说自己不是一直和林晚在一起吗，从家里送到车站。
    objective=陆叔故意修改林晚记忆的 Gaslighting 起点
    info_delta=陆叔开始说谎
- `SC02-B04` [REACTION] importance=critical requires_reaction=True
    林晚因记忆模糊开始短暂怀疑自己，随后抓住茶几划痕与伞骨线索。
    objective=让观众看到陆叔正在 Gaslight 林晚
- `SC02-B05` [REVEAL] importance=critical requires_reaction=True
    陆叔口袋轮廓显现长条状硬物，像是断伞骨。
    objective=把怀疑推向证据
    info_delta=口袋硬物
- `SC02-B06` [REVEAL] importance=critical requires_reaction=True
    玄关地板有一片带暗红痕迹的水渍与纤维碎屑。
    objective=把伞骨与水渍、鞋底线索串联
    info_delta=暗红纤维碎屑
- `SC02-B07` [ESCALATION] importance=critical requires_reaction=True
    陆叔的笑容第一次完全消失，说林晚累了，好好睡一觉。
    objective=威胁浮出水面，Gaslighting 升级
- `SC02-B08` [REVERSAL] importance=critical requires_reaction=True
    林晚后退撞到茶几，水瓶滚落，带起暗红色纤维碎屑飘落。
    objective=林晚的恐惧成为反驳陆叔谎言的证据
    info_delta=碎屑与伞骨同源
- `SC02-B09` [HOOK] importance=critical requires_reaction=True
    陆叔的目光瞬间锁定那片飘落的碎屑，手停在半空。
    objective=集尾强钩子，真相仍藏在迷雾中
- `D020` **陆叔** [OBJECTIVE_FACT] contradicts=[] notice=False
    晚晚，你看看你，跑那么快做什么？脸色这么差，来，先坐下，陆叔给你洗个苹果。
- `D021` **林晚** [UNCERTAIN_CLAIM] contradicts=[] notice=False
    陆叔，我……我刚才在车站，好像看到一把红色的伞。
- `D022` **陆叔** [OBJECTIVE_FACT] contradicts=[] notice=False
    红伞？这阴天，车站里打伞的人多了去了。你是不是太累了，眼花了？
- `D023` **林晚** [UNCERTAIN_CLAIM] contradicts=[] notice=False
    陆叔，我早上出门的时候……是不是忘了什么？我好像……不记得把伞放在哪里了。
- `D024` **陆叔** [OBJECTIVE_FACT] contradicts=[] notice=False
    伞？你哪来的伞？你不是一直不喜欢带伞吗？
- `D025` **林晚** [QUESTION] contradicts=[] notice=False
    陆叔，你口袋里……是什么？
- `D026` **陆叔** [DECEPTION] contradicts=['SC02-B05', 'SC01-B10'] notice=True
    这个？修车用的工具，一根旧的撬棍头，顺手揣兜里忘了。
- `D027` **陆叔** [DECEPTION] contradicts=['SC02-B03'] notice=True
    晚晚，你累了。真的累了。听陆叔的话，好好睡一觉。睡醒了，就什么都记不起来了。
- `D028` **林晚** [QUESTION] contradicts=[] notice=False
    陆叔……你早上，是不是去过车站？很早……比我还早？
- `D029` **陆叔** [DECEPTION] contradicts=['SC01-B03', 'SC01-B08', 'SC02-B02'] notice=True
    晚晚，你说什么呢？陆叔不是一直和你在一起吗？从家里送你到车站，然后一起进的候车室。你忘了？

## SceneTransitionContracts

- `E01_SC001` → `E01_SC002` [RESOLVED] time=later location_change=True
    event=林晚发现包扣被重新动过、断伞骨不见了，决定不上车，对陆叔说忘了拿一样东西先回去；陆叔没有劝她登车，反而立刻同意。
    causal=她意识到继续上车意味着失去验证陆叔的机会，主动选择回家试探。
    elapsed=约半小时，从车站步行返回公寓
