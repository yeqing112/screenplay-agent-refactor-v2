#!/usr/bin/env python3
"""
Screenplay Agent 全面审计脚本
用法: python3 run_audit.py
"""
import sys, json, os, re, ast, time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import httpx

# ── 从项目 config 获取 LLM 配置 ──
import config as cfg
API_KEY = cfg.OPENAI_API_KEY
BASE_URL = cfg.OPENAI_BASE_URL
MODEL = cfg.LLM_MODEL  # deepseek-v4-flash

print(f"🔍 使用模型: {MODEL}")
print(f"  API: {BASE_URL}")
print(f"  Key: {API_KEY[:8]}...{API_KEY[-4:]}")


def llm_call(prompt: str, max_tokens: int = 16000) -> str:
    """直接调用 LLM（不经过项目层，避免 system prompt 干扰）。"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个代码审计专家。精确、专业、不啰嗦。严格按照用户要求的 JSON 格式输出，不要添加额外解释。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    for attempt in range(3):
        try:
            resp = httpx.post(
                f"{BASE_URL}/chat/completions",
                headers=headers, json=payload, timeout=300
            )
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"  [throttle] 429, retry in {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            return f'[ERROR] LLM call failed: {e}'
    return '[ERROR] Max retries exceeded'


def llm_json(prompt: str, max_tokens: int = 16000) -> dict:
    """调用 LLM 并解析 JSON 输出。"""
    content = llm_call(prompt, max_tokens)
    if content.startswith("[ERROR]"):
        return {"error": content}
    # 提取 JSON
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass
    try:
        return json.loads(content)
    except:
        return {"error": f"Failed to parse JSON", "raw": content[:1000]}


def get_source_files():
    """获取所有需要审计的 Python 源文件。"""
    files = []
    # 各目录
    for dir_name in ["agents", "core", "models", "genres"]:
        dir_path = ROOT / dir_name
        if dir_path.exists():
            for f in sorted(dir_path.glob("*.py")):
                if f.name != "__init__.py" or f.stat().st_size > 100:
                    files.append(f)
    # 根目录
    for f_name in ["cli.py", "config.py", "run_pipeline.py"]:
        f = ROOT / f_name
        if f.exists():
            files.append(f)
    # 排除自身
    return sorted(set(f for f in files if f.name != "run_audit.py"))


def get_prompt_files():
    """获取所有 prompt 模板文件。"""
    prompts_dir = ROOT / "prompts"
    if not prompts_dir.exists():
        return []
    files = []
    for f in sorted(prompts_dir.rglob("*")):
        if f.is_file() and f.suffix in (".txt", ".md", ".json"):
            files.append(f)
    return files


def audit_source_file(filepath: Path) -> dict:
    """审计单个源文件。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return {"file": str(filepath.relative_to(ROOT)), "error": str(e), "overall": {"score": 0}}

    rel_path = str(filepath.relative_to(ROOT))
    loc = len(content.splitlines())
    content_trunc = content[:12000]  # 控制 prompt 长度
    trunc_note = f"\n(truncated from {len(content)} chars)" if len(content) > 12000 else ""

    audit_prompt = f"""请审计以下 Python 源文件。

## 文件
{rel_path} ({loc} 行){trunc_note}

## 代码
```python
{content_trunc}
```

## 审计维度（每项 1-10 分，需给出 issue 和 suggestion）

输出严格 JSON 格式：
```json
{{
  "error_handling": {{"score": 1-10, "issues": ["issue"], "suggestions": ["suggestion"]}},
  "type_safety": {{"score": 1-10, "issues": [], "suggestions": []}},
  "architecture": {{"score": 1-10, "issues": [], "suggestions": []}},
  "security": {{"score": 1-10, "issues": [], "suggestions": []}},
  "maintainability": {{"score": 1-10, "issues": [], "suggestions": []}},
  "overall": {{"score": 1-10, "summary": "一句话总结"}}
}}
```"""

    result = llm_json(audit_prompt, max_tokens=8000)
    result["file"] = rel_path
    result["loc"] = loc
    return result


def audit_prompt_file(filepath: Path) -> dict:
    """审计单个 prompt 模板文件。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return {"file": str(filepath.relative_to(ROOT)), "error": str(e), "overall": {"score": 0}}

    rel_path = str(filepath.relative_to(ROOT))
    content_trunc = content[:8000]
    trunc_note = f"\n(truncated from {len(content)} chars)" if len(content) > 8000 else ""

    audit_prompt = f"""请审计以下 Prompt 模板文件。

## 文件
{rel_path} ({len(content)} 字符){trunc_note}

## 内容
```
{content_trunc}
```

## 审计维度（每项 1-10 分）

输出严格 JSON 格式：
```json
{{
  "completeness": {{"score": 1-10, "issues": [], "suggestions": []}},
  "consistency": {{"score": 1-10, "issues": [], "suggestions": []}},
  "llm_reliability": {{"score": 1-10, "issues": [], "suggestions": []}},
  "maintainability": {{"score": 1-10, "issues": [], "suggestions": []}},
  "overall": {{"score": 1-10, "summary": "一句话总结"}}
}}
```"""

    result = llm_json(audit_prompt, max_tokens=6000)
    result["file"] = rel_path
    result["size"] = len(content)
    return result


def audit_architecture() -> dict:
    """审计整体架构和数据模型。"""
    files = get_source_files()

    # 收集关键架构信息
    models_content = ""
    for f in sorted((ROOT / "models").glob("*.py")):
        if f.name not in ("__init__.py", "base.py"):
            models_content += f"\n### {f.name}\n"
            models_content += f.read_text(encoding="utf-8")[:3000] + "\n"

    pipeline = (ROOT / "run_pipeline.py").read_text(encoding="utf-8")[:5000] if (ROOT / "run_pipeline.py").exists() else ""
    cli = (ROOT / "cli.py").read_text(encoding="utf-8")[:5000] if (ROOT / "cli.py").exists() else ""
    config_text = (ROOT / "config.py").read_text(encoding="utf-8")[:3000] if (ROOT / "config.py").exists() else ""

    arch_prompt = f"""请审计 Screenplay Agent 的架构和数据模型。

## 数据模型
{models_content[:15000]}

## Pipeline 编排
```python
{pipeline[:5000]}
```

## CLI
```python
{cli[:5000]}
```

## 配置
```python
{config_text[:3000]}
```

输出 JSON：
```json
{{
  "db_schema": {{"score": 1-10, "issues": [], "suggestions": []}},
  "pipeline_design": {{"score": 1-10, "issues": [], "suggestions": []}},
  "config_management": {{"score": 1-10, "issues": [], "suggestions": []}},
  "cli_design": {{"score": 1-10, "issues": [], "suggestions": []}},
  "overall_architecture": {{"score": 1-10, "issues": [], "suggestions": []}},
  "test_coverage": {{"score": 1-10, "issues": [], "suggestions": []}}
}}
```"""

    return llm_json(arch_prompt, max_tokens=12000)


def generate_report(src_results: list, pmt_results: list, arch_result: dict) -> str:
    """生成最终审计报告。"""
    lines = []
    lines.append(f"# Screenplay Agent 全面审计报告\n")
    lines.append(f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **审计模型**: {MODEL}")
    lines.append(f"- **源文件**: {len(src_results)} | **Prompt 文件**: {len(pmt_results)}")

    # ── 计算综合评分 ──
    def _score(item, key):
        d = item.get(key, {})
        return d.get("score") if isinstance(d, dict) and isinstance(d.get("score"), (int, float)) else None

    src_scores = [s for r in src_results if (s := _score(r, "overall")) is not None]
    pmt_scores = [s for r in pmt_results if (s := _score(r, "overall")) is not None]
    arch_s = _score(arch_result, "overall_architecture") if arch_result else None

    avg_src = sum(src_scores) / len(src_scores) if src_scores else 0
    avg_pmt = sum(pmt_scores) / len(pmt_scores) if pmt_scores else 0

    lines.append(f"\n## 摘要\n")
    lines.append(f"| 维度 | 综合评分 |")
    lines.append(f"|------|---------|")
    lines.append(f"| 📝 代码质量 ({len(src_scores)} 文件) | **{avg_src:.1f}/10** |")
    lines.append(f"| 📋 提示词质量 ({len(pmt_scores)} 文件) | **{avg_pmt:.1f}/10** |")
    lines.append(f"| 🏗️ 架构设计 | **{arch_s}/10** |" if arch_s else "")

    # ── Top Issues ──
    all_issues = []
    for r in src_results:
        file = r.get("file", "?")
        for dim in ["error_handling", "type_safety", "architecture", "security", "maintainability"]:
            dim_data = r.get(dim, {})
            if not isinstance(dim_data, dict): continue
            for iss in dim_data.get("issues", []):
                all_issues.append((file, dim, iss, dim_data.get("score", 5)))

    all_issues.sort(key=lambda x: x[3])
    lines.append(f"\n## Top 严重问题\n")
    for i, (file, dim, issue, score) in enumerate(all_issues[:10], 1):
        sev = "🔴" if score < 4 else "🟡" if score < 7 else "🟢"
        lines.append(f"{i}. {sev} **{file}** [{dim}] {issue}")

    # ── A. 代码质量 ──
    lines.append(f"\n---\n## A. 代码质量审查\n")
    lines.append("| 文件 | LOC | 错误处理 | 类型安全 | 架构 | 安全 | 可维护 | 总分 |")
    lines.append("|------|-----|---------|---------|------|------|--------|------|")
    for r in sorted(src_results, key=lambda x: x.get("file", "")):
        file = r.get("file", "")
        if r.get("error"):
            lines.append(f"| {file} | — | — | — | — | — | — | ❌ {r['error']} |")
            continue
        eh = _score(r, "error_handling") or "—"
        ts = _score(r, "type_safety") or "—"
        ar = _score(r, "architecture") or "—"
        sc = _score(r, "security") or "—"
        mt = _score(r, "maintainability") or "—"
        ov = _score(r, "overall") or "—"
        loc = r.get("loc", 0)
        lines.append(f"| {file} | {loc} | {eh} | {ts} | {ar} | {sc} | {mt} | **{ov}** |")

    lines.append(f"\n### 详细审查\n")
    for r in sorted(src_results, key=lambda x: x.get("file", "")):
        file = r.get("file", "")
        if r.get("error"):
            lines.append(f"\n#### {file} — ❌ {r['error']}")
            continue
        ov = _score(r, "overall")
        summary = (r.get("overall") or {}).get("summary", "")
        lines.append(f"\n#### {file} (评分: {ov}/10)" + (f"\n> {summary}" if summary else ""))
        for dim, label in [("error_handling", "错误处理"), ("type_safety", "类型安全"),
                           ("architecture", "架构"), ("security", "安全"), ("maintainability", "可维护")]:
            d = r.get(dim, {})
            if not isinstance(d, dict): continue
            s = d.get("score")
            if s is None: continue
            icon = "🟢" if s >= 7 else "🟡" if s >= 4 else "🔴"
            lines.append(f"\n{icon} **{label}**: {s}/10")
            for iss in d.get("issues", [])[:3]:
                lines.append(f"  - {iss}")
            sugs = d.get("suggestions", [])[:2]
            if sugs:
                lines.append(f"  → {'; '.join(sugs)}")

    # ── B. 提示词 ──
    lines.append(f"\n---\n## B. 提示词质量审查\n")
    lines.append("| 文件 | 大小 | 完整性 | 一致性 | LLM可靠性 | 可维护 | 总分 |")
    lines.append("|------|------|--------|--------|----------|--------|------|")
    for r in sorted(pmt_results, key=lambda x: x.get("file", "")):
        file = r.get("file", "")
        if r.get("error"):
            lines.append(f"| {file} | — | — | — | — | — | ❌ |")
            continue
        cp = _score(r, "completeness") or "—"
        cs = _score(r, "consistency") or "—"
        lr = _score(r, "llm_reliability") or "—"
        mt = _score(r, "maintainability") or "—"
        ov = _score(r, "overall") or "—"
        sz = r.get("size", 0)
        lines.append(f"| {file} | {sz}B | {cp} | {cs} | {lr} | {mt} | **{ov}** |")

    lines.append(f"\n### 详细审查\n")
    for r in sorted(pmt_results, key=lambda x: x.get("file", "")):
        file = r.get("file", "")
        if r.get("error"): continue
        ov = _score(r, "overall")
        summary = (r.get("overall") or {}).get("summary", "")
        lines.append(f"\n#### {file} (评分: {ov}/10)" + (f"\n> {summary}" if summary else ""))

    # ── D. 架构 ──
    lines.append(f"\n---\n## D. 架构与数据模型审查\n")
    if arch_result:
        for dim, label in [("db_schema", "数据库 Schema"), ("pipeline_design", "Pipeline 设计"),
                           ("config_management", "配置管理"), ("cli_design", "CLI 设计"),
                           ("overall_architecture", "整体架构"), ("test_coverage", "测试覆盖")]:
            d = arch_result.get(dim, {})
            if not isinstance(d, dict): continue
            s = d.get("score")
            if s is None: continue
            icon = "🟢" if s >= 7 else "🟡" if s >= 4 else "🔴"
            lines.append(f"{icon} **{label}**: {s}/10")
            for iss in d.get("issues", [])[:4]:
                lines.append(f"  - {iss}")
            sugs = d.get("suggestions", [])[:3]
            if sugs:
                lines.append(f"  → {'; '.join(sugs)}")
            lines.append("")

    # ── E. 建议 ──
    lines.append(f"---\n## E. 建议优先级\n")
    p0, p1, p2 = [], [], []

    for r in src_results:
        file = r.get("file", "")
        for dim in ["error_handling", "type_safety", "architecture", "security", "maintainability"]:
            d = r.get(dim, {})
            if not isinstance(d, dict): continue
            s = d.get("score")
            for sug in d.get("suggestions", []):
                if s is not None and s < 4:
                    p0.append(f"🔴 **P0** [{file}] {sug}")
                elif s is not None and s < 7:
                    p1.append(f"🟡 **P1** [{file}] {sug}")
                else:
                    p2.append(f"🟢 **P2** [{file}] {sug}")

    if arch_result:
        for dim in ["db_schema", "pipeline_design", "config_management", "cli_design", "overall_architecture", "test_coverage"]:
            d = arch_result.get(dim, {})
            if not isinstance(d, dict): continue
            s = d.get("score")
            for sug in d.get("suggestions", []):
                if s is not None and s < 4:
                    p0.append(f"🔴 **P0** [架构:{dim}] {sug}")
                elif s is not None and s < 7:
                    p1.append(f"🟡 **P1** [架构:{dim}] {sug}")
                else:
                    p2.append(f"🟢 **P2** [架构:{dim}] {sug}")

    for title, items in [("P0 — 必须修复", p0), ("P1 — 建议修复", p1), ("P2 — 可优化", p2)]:
        lines.append(f"### {title} ({len(items)} 项)\n")
        for item in items[:10]:
            lines.append(f"{item}\n")
        if len(items) > 10:
            lines.append(f"… 还有 {len(items) - 10} 项\n")

    lines.append(f"\n---\n*报告由 Audit Agent 自动生成*")
    return "\n".join(lines)


def main():
    print(f"\n{'='*50}")
    print(f"Screenplay Agent 全面审计")
    print(f"{'='*50}\n")

    src_files = get_source_files()
    pmt_files = get_prompt_files()
    print(f"📁 Python 源文件: {len(src_files)} 个")
    print(f"📁 Prompt 模板: {len(pmt_files)} 个\n")

    # Phase A
    print(f"{'='*50}")
    print("Phase A: 代码质量审查")
    print(f"{'='*50}")
    src_results = []
    for i, f in enumerate(src_files, 1):
        rel = str(f.relative_to(ROOT))
        print(f"  [{i}/{len(src_files)}] {rel}...", end=" ", flush=True)
        result = audit_source_file(f)
        src_results.append(result)
        score = _score(result, "overall")
        if result.get("error"):
            print(f"❌ {result['error'][:50]}")
        else:
            print(f"评分: {score}/10")

    # Phase B
    print(f"\n{'='*50}")
    print("Phase B: 提示词质量审查")
    print(f"{'='*50}")
    pmt_results = []
    for i, f in enumerate(pmt_files, 1):
        rel = str(f.relative_to(ROOT))
        print(f"  [{i}/{len(pmt_files)}] {rel}...", end=" ", flush=True)
        result = audit_prompt_file(f)
        pmt_results.append(result)
        score = _score(result, "overall")
        if result.get("error"):
            print(f"❌ {result['error'][:50]}")
        else:
            print(f"评分: {score}/10")

    # Phase D
    print(f"\n{'='*50}")
    print("Phase D: 架构与数据模型审查")
    print(f"{'='*50}")
    print("  分析中...", end=" ", flush=True)
    arch_result = audit_architecture()
    score = _score(arch_result, "overall_architecture")
    print(f"评分: {score}/10\n")

    # 生成报告
    print(f"{'='*50}")
    print("生成报告...", end=" ", flush=True)
    report = generate_report(src_results, pmt_results, arch_result)
    report_path = ROOT / "AUDIT_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(f" ✔ {report_path}")

    # 备份原始数据
    data = {
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
        "source_results": src_results,
        "prompt_results": pmt_results,
        "arch_result": arch_result,
    }
    (ROOT / "audit_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  数据备份: {ROOT / 'audit_data.json'}")

    print(f"\n{'='*50}")
    print(f"✔ 审计完成！报告: {report_path}")
    print(f"{'='*50}")


def _score(item, key):
    """Safely extract numeric score from nested dict."""
    if not isinstance(item, dict): return None
    d = item.get(key, {})
    if not isinstance(d, dict): return None
    s = d.get("score")
    return s if isinstance(s, (int, float)) else None


if __name__ == "__main__":
    main()
