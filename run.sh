#!/bin/bash
# 编剧 Agent 系统 - 快速启动脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "创建虚拟环境..."
    python3.11 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# 激活环境
source .venv/bin/activate

# 检查 Ollama 连通性
echo "检查 Ollama 连通性..."
if curl -s --connect-timeout 3 http://10.126.126.2:11434/api/tags > /dev/null 2>&1; then
    echo "  ✓ Ollama 可达"
else
    echo "  ⚠ Ollama 不可达 (向量索引功能降级)"
fi

# 运行 CLI
python cli.py "$@"
