import importlib
from typing import Any, Callable, Optional
from pydantic import BaseModel


class NodeInput(BaseModel):
    name: str
    label: str
    type: str = "string"  # string | int | bool | select
    required: bool = True
    default: Any = None
    options: Optional[list[str]] = None  # for select type


class NodeOutput(BaseModel):
    name: str
    label: str
    type: str = "string"


class NodeSpec(BaseModel):
    name: str
    label: str
    category: str
    description: str = ""
    handler_path: str  # e.g. "nodes.handlers.outline"
    inputs: list[NodeInput] = []
    outputs: list[NodeOutput] = []
    agent_class: Optional[str] = None
    default_prompt: Optional[str] = None


REGISTRY: dict[str, NodeSpec] = {}


def register(spec: NodeSpec) -> None:
    REGISTRY[spec.name] = spec


def get_handler(name: str) -> Callable | None:
    spec = REGISTRY.get(name)
    if not spec:
        return None
    mod = importlib.import_module(spec.handler_path)
    return getattr(mod, "run", None)


# --- 注册所有节点 ---

register(NodeSpec(
    name="ingest",
    label="导入小说",
    category="input",
    description="将 TXT 文件导入为 Book 记录",
    handler_path="nodes.handlers.ingest",
    inputs=[NodeInput(name="filepath", label="文件路径", type="string")],
    outputs=[NodeOutput(name="book_id", label="书籍 ID", type="string")],
    agent_class="core.ingest.ingest",
))

register(NodeSpec(
    name="read",
    label="阅读分析",
    category="analysis",
    description="逐章分析，提取角色、事件、伏笔",
    handler_path="nodes.handlers.read",
    inputs=[NodeInput(name="book_id", label="书籍 ID", type="string")],
    agent_class="agents.reader.ReaderAgent",
))

register(NodeSpec(
    name="bible",
    label="小说圣经",
    category="analysis",
    description="汇总章节分析，生成小说圣经",
    handler_path="nodes.handlers.bible",
    inputs=[NodeInput(name="book_id", label="书籍 ID", type="string")],
    agent_class="agents.bible.BibleAgent",
))

register(NodeSpec(
    name="resolve",
    label="别名归并",
    category="analysis",
    description="角色别名归并，消除同名歧义",
    handler_path="nodes.handlers.resolve",
    inputs=[NodeInput(name="book_id", label="书籍 ID", type="string")],
))

register(NodeSpec(
    name="portrait",
    label="人物画像",
    category="analysis",
    description="生成人物外貌、造型、生图提示词",
    handler_path="nodes.handlers.portrait",
    inputs=[NodeInput(name="book_id", label="书籍 ID", type="string")],
    agent_class="agents.portrait.PortraitAgent",
))

register(NodeSpec(
    name="adapt",
    label="改编规划",
    category="adapt",
    description="生成赛道改编方案",
    handler_path="nodes.handlers.adapt",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="genre", label="赛道", type="select",
                  default="short_drama",
                  options=["short_drama", "manhua", "movie", "tv_series"]),
    ],
))

register(NodeSpec(
    name="outline",
    label="分集大纲",
    category="adapt",
    description="生成分集大纲（全部分集）",
    handler_path="nodes.handlers.outline",
    inputs=[NodeInput(name="book_id", label="书籍 ID", type="string")],
    agent_class="agents.outline.OutlineAgent",
))

register(NodeSpec(
    name="script",
    label="剧本生成",
    category="script",
    description="按集生成剧本",
    handler_path="nodes.handlers.script",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="episode", label="集数", type="int"),
        NodeInput(name="genre", label="赛道", type="select",
                  default="short_drama",
                  options=["short_drama", "manhua", "movie", "tv_series"]),
    ],
    agent_class="agents.scriptwriter.ScriptwriterAgent",
))

register(NodeSpec(
    name="rewrite",
    label="剧本打磨",
    category="script",
    description="对剧本做二次打磨",
    handler_path="nodes.handlers.rewrite",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="episode", label="集数", type="int"),
    ],
    agent_class="agents.rewrite.RewriteAgent",
))

register(NodeSpec(
    name="check",
    label="剧本质检",
    category="script",
    description="检查剧本的人物一致性、设定冲突等",
    handler_path="nodes.handlers.check",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="episode", label="集数", type="int"),
    ],
    agent_class="agents.qa.QAAgent",
))

register(NodeSpec(
    name="era_scan",
    label="时代规范",
    category="vision",
    description="扫描时代妆造规范",
    handler_path="nodes.handlers.era_scan",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="genre", label="赛道", type="select",
                  default="short_drama",
                  options=["short_drama", "manhua", "movie", "tv_series"]),
    ],
))

register(NodeSpec(
    name="props",
    label="道具提取",
    category="vision",
    description="提取指定集的道具并生成视觉提示词",
    handler_path="nodes.handlers.props",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="episode", label="集数", type="int"),
        NodeInput(name="genre", label="赛道", type="select",
                  default="short_drama",
                  options=["short_drama", "manhua", "movie", "tv_series"]),
    ],
))

register(NodeSpec(
    name="locations",
    label="场景提取",
    category="vision",
    description="提取指定集的场景并生成视觉提示词",
    handler_path="nodes.handlers.locations",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="episode", label="集数", type="int"),
        NodeInput(name="genre", label="赛道", type="select",
                  default="short_drama",
                  options=["short_drama", "manhua", "movie", "tv_series"]),
    ],
))

register(NodeSpec(
    name="makeup",
    label="定妆照",
    category="vision",
    description="精调指定集的人物定妆照提示词",
    handler_path="nodes.handlers.makeup",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="episode", label="集数", type="int"),
        NodeInput(name="genre", label="赛道", type="select",
                  default="short_drama",
                  options=["short_drama", "manhua", "movie", "tv_series"]),
    ],
))

register(NodeSpec(
    name="storyboard",
    label="分镜表",
    category="vision",
    description="按场景生成结构化分镜表",
    handler_path="nodes.handlers.storyboard",
    inputs=[
        NodeInput(name="book_id", label="书籍 ID", type="string"),
        NodeInput(name="episode", label="集数", type="int"),
        NodeInput(name="genre", label="赛道", type="select",
                  default="short_drama",
                  options=["short_drama", "manhua", "movie", "tv_series"]),
    ],
    agent_class="agents.storyboard.StoryboardAgent",
))

