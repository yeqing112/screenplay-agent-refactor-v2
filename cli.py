"""Screenplay Agent CLI - 编剧 Agent 系统命令行工具。"""
import sys
import time
from pathlib import Path
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint

app = typer.Typer(help="编剧 Agent 系统 - 长篇小说改编短剧/漫剧工具", pretty_exceptions_enable=False)
console = Console()


def _init():
    from models import init_db
    init_db()


@app.command()
def genres():
    """列出所有可用赛道。"""
    from genres import list_genres
    table = Table(title="可用赛道")
    table.add_column("Key", style="cyan")
    table.add_column("图标")
    table.add_column("名称")
    table.add_column("单集时长")
    table.add_column("集数")
    table.add_column("受众")

    for g in list_genres():
        table.add_row(g["key"], g["icon"], g["description"],
                      g["duration"], g["count"], g["audience"])
    console.print(table)


@app.command()
def ingest(filepath: str = typer.Argument(..., help="小说文件路径")):
    """导入小说并自动切章。"""
    _init()
    from core.ingest import ingest as do_ingest
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("导入中...")
        result = do_ingest(filepath)
    console.print(f"\n[green]✓[/] 导入成功: {result['title']}")
    console.print(f"  章节: {result['chapters']}  总字数: {result['words']:,}")
    console.print(f"  Book ID: {result['book_id']}")


@app.command()
def read(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    start: int = typer.Option(None, help="起始章节"),
    end: int = typer.Option(None, help="结束章节"),
):
    """逐章精读，提取人物、事件、场景。"""
    _init()
    from agents.reader import ReaderAgent
    agent = ReaderAgent(book_id)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("逐章分析中...")
        result = agent.run(start_ch=start, end_ch=end)
    console.print(f"\n[green]✓[/] 分析完成: {result['processed']} 章")
    if result.get("errors"):
        console.print(f"  [red]✗ {len(result['errors'])} 章失败[/]")
    console.print(f"  发现角色: {result['characters']}")


@app.command()
def bible(book_id: int = typer.Argument(..., help="书籍 ID")):
    """生成小说圣经。"""
    _init()
    from agents.bible import BibleAgent
    agent = BibleAgent(book_id)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("生成小说圣经...")
        output = agent.run()
    console.print(f"\n[green]✓[/] 小说圣经已生成: {output}")


@app.command()
def adapt(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道: short_drama/manhua/movie/tv_series"),
):
    """生成改编方案（按赛道）。"""
    _init()
    from agents.adapter import AdapterAgent
    agent = AdapterAgent(book_id, genre=genre)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"生成{genre}改编方案...")
        output = agent.run()
    console.print(f"\n[green]✓[/] 改编方案已生成: {output}")


@app.command()
def outline(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    adaptation_type: str = typer.Option("extractive", "--type", "-t",
        help="改编类型: faithful(忠实)/extractive(提取)/loose(灵感)"),
):
    """生成分集大纲。"""
    _init()
    from agents.outline import OutlineAgent
    valid_types = ["faithful", "extractive", "loose"]
    if adaptation_type not in valid_types:
        console.print(f"[red]无效改编类型: {adaptation_type}。可选: {', '.join(valid_types)}[/]")
        raise typer.Exit(1)
    agent = OutlineAgent(book_id, adaptation_type=adaptation_type)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"生成{adaptation_type}型分集大纲...")
        output = agent.run()
    console.print(f"\n[green]✓[/] 分集大纲已生成: {output}")


@app.command()
def script(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    episode: int = typer.Option(..., "--episode", "-e", help="集数"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道"),
):
    """生成指定集剧本（按赛道）。"""
    _init()
    from agents.scriptwriter import ScriptwriterAgent
    agent = ScriptwriterAgent(book_id, genre=genre)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"生成第{episode}集剧本...")
        output = agent.run(episode)
    console.print(f"\n[green]✓[/] 剧本已生成: {output}")


@app.command()
def resolve(
    book_id: int = typer.Argument(..., help="书籍 ID"),
):
    """角色别名归并：将同一角色的不同称呼自动合并。"""
    _init()
    from core.alias_resolver import resolve_aliases
    from models import Session
    with Session() as s:
        result = resolve_aliases(book_id, s)
    merged_count = sum(1 for v in result.values() if len(v) > 1)
    console.print(f"\n[green]✓[/] 别名归并完成，{merged_count} 组角色被合并")


@app.command()
def portrait(
    book_id: int = typer.Argument(..., help="书籍 ID"),
):
    """生成人物画像（外貌、造型、生图提示词）。"""
    _init()
    from agents.portrait import PortraitAgent
    agent = PortraitAgent(book_id)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("生成人物画像...")
        output = agent.run()
    console.print(f"\n[green]✓[/] 人物画像已生成: {output}")


@app.command()
def profiles(
    book_id: int = typer.Argument(..., help="书籍 ID"),
):
    """查看人物画像列表。"""
    _init()
    from models import Session, CharacterProfile
    with Session() as s:
        profiles = s.query(CharacterProfile).filter(
            CharacterProfile.book_id == book_id
        ).order_by(CharacterProfile.importance.desc()).all()
        if not profiles:
            console.print("[dim]暂无画像，请先运行 portrait[/]")
            return
        table = Table(title=f"人物画像 (Book #{book_id})")
        table.add_column("角色", style="cyan")
        table.add_column("身份")
        table.add_column("性别")
        table.add_column("年龄")
        table.add_column("气质", style="green")
        table.add_column("氛围")
        table.add_column("出场")
        for p in profiles:
            table.add_row(
                p.name, p.identity[:15], p.gender, p.age_range,
                p.temperament[:20], p.vibe[:15], p.chapter_range,
            )
        console.print(table)


@app.command()
def stages(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    name: str = typer.Option(None, "--name", "-n", help="角色名（不指定则显示全部）"),
):
    """查看人物阶段化画像。"""
    _init()
    from models import Session, CharacterStage
    with Session() as s:
        q = s.query(CharacterStage).filter(CharacterStage.book_id == book_id)
        if name:
            q = q.filter(CharacterStage.character_name == name)
        stages = q.order_by(CharacterStage.character_name, CharacterStage.chapter_start).all()
        if not stages:
            console.print("[dim]暂无阶段画像，请先运行 portrait[/]")
            return
        table = Table(title=f"人物阶段画像 (Book #{book_id})")
        table.add_column("角色", style="cyan")
        table.add_column("阶段")
        table.add_column("章节范围")
        table.add_column("时间线")
        table.add_column("身份", style="green")
        table.add_column("年龄")
        table.add_column("穿着", style="yellow")
        for st in stages:
            table.add_row(
                st.character_name, st.stage_name,
                f"{st.chapter_start}-{st.chapter_end}",
                st.timeline[:15], st.identity[:20],
                st.age_description[:15], st.signature_outfit[:25],
            )
        console.print(table)


@app.command()
def rewrite(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    episode: int = typer.Option(..., "--episode", "-e", help="集数"),
    ep_end: int = typer.Option(None, "--ep-end", help="结束集（批量）"),
):
    """爆款改稿：对已有剧本做二次打磨。支持单集或连续多集。"""
    _init()
    from agents.rewrite import RewriteAgent
    agent = RewriteAgent(book_id)

    if ep_end:
        for ep in range(episode, ep_end + 1):
            with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
                prog.add_task(f"改稿第{ep}集...")
                output = agent.run(ep)
            console.print(f"  [green]✓[/] 第{ep}集: {output}")
    else:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
            task = prog.add_task(f"改稿第{episode}集...")
            output = agent.run(episode)
        console.print(f"\n[green]✓[/] 改稿完成: {output}")


@app.command()
def check(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    episode: int = typer.Option(..., "--episode", "-e", help="集数"),
    ep_end: int = typer.Option(None, "--ep-end", help="结束集（批量）"),
):
    """质检指定集剧本。支持单集或连续多集。每次质检后自动写文件+刷新汇总报告。"""
    _init()
    from agents.qa import QAAgent
    agent = QAAgent(book_id)

    if ep_end:
        for ep in range(episode, ep_end + 1):
            with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
                prog.add_task(f"质检第{ep}集...")
                result = agent.run(ep)
            _print_qa_result(ep, result)
        # 刷新生效汇总报告
        from models import Session, Book
        with Session() as s:
            book = s.get(Book, book_id)
        if book:
            report_path = agent.generate_report()
            console.print(f"\n[green]✓[/] 汇总报告: {report_path}")
    else:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
            task = prog.add_task(f"质检第{episode}集...")
            result = agent.run(episode)
        _print_qa_result(episode, result)
        report_path = agent.generate_report()
        console.print(f"\n[green]✓[/] 报告已更新: {report_path}")


def _print_qa_result(ep, result):
    """打印单集质检结果。"""
    errors = result.get("errors", [])
    score = result.get("overall_score", "?")
    console.print(f"  [yellow]📋 第{ep}集 (得分: {score})[/]")
    if errors:
        for e in errors:
            color = {"high": "red", "medium": "yellow", "low": "dim"}.get(e.get("severity", ""), "white")
            console.print(f"    [{color}][{e.get('type','')}] {e.get('description','')}[/]")
    else:
        console.print("    [green]无问题[/]")


@app.command()
def qa_report(
    book_id: int = typer.Argument(..., help="书籍 ID"),
):
    """刷新并查看质检汇总报告。"""
    _init()
    from agents.qa import QAAgent
    agent = QAAgent(book_id)
    report_path = agent.generate_report()
    report = Path(report_path).read_text(encoding="utf-8")
    console.print(report)
    console.print(f"\n[green]✓[/] 报告文件: {report_path}")


@app.command()
def status():
    """查看所有书籍状态。"""
    _init()
    from models import Session, Book
    with Session() as s:
        books = s.query(Book).all()
        if not books:
            console.print("[dim]暂无书籍[/]")
            return
        table = Table(title="书籍状态")
        table.add_column("ID", style="cyan")
        table.add_column("标题")
        table.add_column("章节数")
        table.add_column("字数")
        table.add_column("状态", style="green")
        for b in books:
            table.add_row(str(b.id), b.title, str(b.chapter_count),
                          f"{b.total_words:,}", b.status)
        console.print(table)


@app.command()
def era_scan(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道"),
):
    """扫描时代妆造规范。"""
    _init()
    from agents.scene_setup import SceneSetupAgent
    from models import Session, Book
    agent = SceneSetupAgent(book_id, genre=genre)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("扫描时代规范...")
        agent.run_era_scan()
    console.print(f"\n[green]✓[/] 时代规范已生成")
    with Session() as s:
        book = s.get(Book, book_id)
    agent.save_era_spec_output(book.title)


@app.command()
def props(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    episode: int = typer.Option(..., "--episode", "-e", help="集数"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道"),
):
    """提取指定集的道具并生成视觉提示词。"""
    _init()
    from agents.scene_setup import SceneSetupAgent
    agent = SceneSetupAgent(book_id, genre=genre)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"提取第{episode}集道具...")
        agent.run_props(episode)
    console.print(f"\n[green]✓[/] 第{episode}集道具提示词已生成")


@app.command()
def locations(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    episode: int = typer.Option(..., "--episode", "-e", help="集数"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道"),
):
    """提取指定集的场景并生成视觉提示词。"""
    _init()
    from agents.scene_setup import SceneSetupAgent
    agent = SceneSetupAgent(book_id, genre=genre)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"提取第{episode}集场景...")
        agent.run_locations(episode)
    console.print(f"\n[green]✓[/] 第{episode}集场景提示词已生成")


@app.command()
def makeup(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    episode: int = typer.Option(..., "--episode", "-e", help="集数"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道"),
):
    """精调指定集的人物定妆照提示词。"""
    _init()
    from agents.scene_setup import SceneSetupAgent
    agent = SceneSetupAgent(book_id, genre=genre)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"精调第{episode}集定妆照...")
        agent.run_makeup(episode)
    console.print(f"\n[green]✓[/] 第{episode}集定妆照已生成")


@app.command()
def storyboard(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    episode: int = typer.Option(..., "--episode", "-e", help="集数"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道"),
):
    """生成分镜表。"""
    _init()
    console.print(f"[cyan]生成第{episode}集分镜表...[/]")
    from agents.storyboard import StoryboardAgent
    shots = StoryboardAgent(book_id, genre=genre).run(episode)
    console.print(f"[green]✓[/] 共生成 {len(shots)} 个镜头")


@app.command()
def scene_setup(
    book_id: int = typer.Argument(..., help="书籍 ID"),
    episode: int = typer.Option(..., "--episode", "-e", help="集数"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道"),
):
    """完整视觉统筹：时代规范 + 道具 + 场景 + 定妆照。

    注意：需要先运行 era_scan（如首次运行则自动执行），
    然后为该集生成道具、场景和定妆照。
    """
    _init()
    from agents.scene_setup import SceneSetupAgent
    agent = SceneSetupAgent(book_id, genre=genre)

    # 1. Era scan (if not exists)
    console.print("[cyan]1/4 检查时代规范...[/]")
    from models import Session, VisualEraSpec
    with Session() as s:
        era = s.query(VisualEraSpec).filter(VisualEraSpec.book_id == book_id).first()
    if not era:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
            task = prog.add_task("扫描时代规范...")
            agent.run_era_scan()
        console.print("  ✓ 时代规范完成")
    else:
        console.print("  ✓ 时代规范已存在，跳过")

    # 2. Props
    console.print("[cyan]2/4 提取道具...[/]")
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"提取第{episode}集道具...")
        agent.run_props(episode)
    console.print("  ✓ 道具完成")

    # 3. Locations
    console.print("[cyan]3/4 提取场景...[/]")
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"提取第{episode}集场景...")
        agent.run_locations(episode)
    console.print("  ✓ 场景完成")

    # 4. Makeup
    console.print("[cyan]4/4 精调定妆照...[/]")
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task(f"精调第{episode}集定妆照...")
        agent.run_makeup(episode)
    console.print("  ✓ 定妆照完成")

    # 保存输出文件
    from models import Session, Book
    with Session() as s:
        book = s.get(Book, book_id)
    agent.save_era_spec_output(book.title)
    agent.save_props_output(book.title)
    agent.save_locations_output(book.title)

    console.print(f"\n[bold green]=== 视觉统筹完成 ===[/]")
    console.print(f"Book ID: {book_id} | Episode: {episode} | Genre: {genre}")


@app.command()
def pipeline(
    filepath: str = typer.Argument(..., help="小说文件路径"),
    genre: str = typer.Option("short_drama", "--genre", "-g", help="赛道"),
    episodes: int = typer.Option(20, help="目标集数"),
):
    """一键运行完整流程。"""
    _init()
    console.print(f"[bold]=== 编剧 Agent 完整流程 ({genre}) ===[/]\n")

    # 1. Ingest
    console.print("[cyan]1/8 导入小说...[/]")
    from core.ingest import ingest as do_ingest
    result = do_ingest(filepath)
    book_id = result["book_id"]
    console.print(f"  ✓ {result['title']} ({result['chapters']}章)\n")

    # 2. Read
    console.print("[cyan]2/8 逐章分析...[/]")
    from agents.reader import ReaderAgent
    ReaderAgent(book_id).run()
    console.print("  ✓ 分析完成\n")

    # 3. Bible
    console.print("[cyan]3/8 生成小说圣经...[/]")
    from agents.bible import BibleAgent
    BibleAgent(book_id).run()
    console.print("  ✓ 小说圣经完成\n")

    # 4. Alias Resolve
    console.print("[cyan]4/7 别名归并...[/]")
    from core.alias_resolver import resolve_aliases
    from models import Session
    with Session() as sess:
        resolve_aliases(book_id, sess)
    console.print("  ✓ 别名归并完成\n")

    # 5. Portrait
    console.print("[cyan]5/7 生成人物画像...[/]")
    from agents.portrait import PortraitAgent
    PortraitAgent(book_id).run()
    console.print("  ✓ 人物画像完成\n")

    # 6. Adapt
    console.print(f"[cyan]6/7 生成{genre}改编方案...[/]")
    from agents.adapter import AdapterAgent
    AdapterAgent(book_id, genre=genre).run()
    console.print("  ✓ 改编方案完成\n")

    # 7. Outline
    console.print("[cyan]7/7 生成分集大纲...[/]")
    from agents.outline import OutlineAgent
    OutlineAgent(book_id).run()
    console.print("  ✓ 分集大纲完成\n")

    # 8. Visual Setup
    console.print("[cyan]7/7 视觉统筹（时代规范 + 道具 + 场景 + 定妆照）...[/]")
    from agents.scene_setup import SceneSetupAgent
    from models import Script
    visual_agent = SceneSetupAgent(book_id, genre=genre)
    visual_agent.run_era_scan()
    visual_agent.save_era_spec_output(result["title"])
    # 为前 3 集生成视觉数据（可按需增加）
    from models import Session
    for ep in range(1, min(episodes, 4) + 1):
        with Session() as sess:
            check_script = sess.query(Script).filter(
                Script.book_id == book_id, Script.episode == ep
            ).first()
        if check_script:
            visual_agent.run_props(ep)
            visual_agent.run_locations(ep)
            visual_agent.run_makeup(ep)
    visual_agent.save_props_output(result["title"])
    visual_agent.save_locations_output(result["title"])
    console.print("  ✓ 视觉统筹完成\n")

    # 9. Storyboard (前3集)
    console.print("[cyan]8/8 分镜表生成...[/]")
    from agents.storyboard import StoryboardAgent
    for ep in range(1, min(episodes, 4) + 1):
        with Session() as sess:
            check_script = sess.query(Script).filter(
                Script.book_id == book_id, Script.episode == ep
            ).first()
        if check_script:
            StoryboardAgent(book_id, genre=genre).run(ep)
    console.print("  ✓ 分镜表完成\n")

    console.print(f"[bold green]=== 全部完成 ===[/]")

    console.print(f"Book ID: {book_id} | Genre: {genre}")
    console.print(f"运行 `python cli.py script {book_id} -e 1 -g {genre}` 生成第一集剧本")


if __name__ == "__main__":
    app()
