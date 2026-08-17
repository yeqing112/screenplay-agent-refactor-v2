"""Prompt 模板管理 - 统一加载和管理所有 prompt 模板。"""
import re
from pathlib import Path
from typing import Optional

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _validate_name(name: str) -> None:
    """验证 prompt 名称，防止路径遍历攻击。"""
    if not name:
        raise ValueError("Prompt name cannot be empty")
    # 只允许字母、数字、下划线、斜杠（用于子目录）、点号
    if not re.match(r'^[\w./-]+$', name):
        raise ValueError(
            f"Invalid prompt name: {name!r}. "
            "Only alphanumeric, underscore, slash, dot, and hyphen allowed."
        )
    # 阻止绝对路径和上级目录
    resolved = (PROMPTS_DIR / f"{name}.txt").resolve()
    if not str(resolved).startswith(str(PROMPTS_DIR.resolve())):
        raise ValueError(
            f"Path traversal detected: {name!r} resolves outside prompts directory"
        )


def load_prompt(name: str, **kwargs) -> str:
    """加载 prompt 模板并替换变量。

    Args:
        name: 模板文件名（相对于 prompts/，不含 .txt）
        **kwargs: 模板变量替换

    Returns:
        渲染后的 prompt 字符串
    """
    _validate_name(name)
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    try:
        template = path.read_text(encoding="utf-8")
    except OSError as e:
        raise IOError(f"Failed to read prompt template {path}: {e}") from e
    if kwargs:
        try:
            template = template.format(**kwargs)
        except KeyError:
            def _replacer(match):
                key = match.group(1).strip()
                return str(kwargs.get(key, ""))
            template = re.sub(r'\{(\w+)\}', _replacer, template)
    return template


def list_prompts() -> list[dict]:
    """列出所有可用 prompt 模板。"""
    prompts = []
    for f in sorted(PROMPTS_DIR.rglob("*.txt")):
        rel = f.relative_to(PROMPTS_DIR)
        prompts.append({
            "name": str(rel.with_suffix("")),
            "path": str(rel),
            "size": f.stat().st_size,
        })
    return prompts
