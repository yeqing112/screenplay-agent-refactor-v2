import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNS_DIR = Path("runs")
WORKFLOWS_DIR = Path("workflow_data")


class NodeRunner:
    """每个节点执行时的上下文管理器。
    负责：
    - 存储执行快照到 runs/ 目录
    - 提供 get_input / set_output / log 接口
    - 记录 raw_llm_response / meta 信息
    """

    def __init__(self, node_type: str, workflow_id: str | None = None):
        self.run_id = str(uuid.uuid4())[:8]
        self.node_type = node_type
        self.workflow_id = workflow_id
        self._inputs: dict = {}
        self._config: dict = {}
        self._outputs: dict = {}
        self._logs: list[str] = []
        self._raw_llm: str | None = None
        self._meta: dict = {}
        self._started_at = datetime.now(timezone.utc)

    # --- input/output ---

    def get_input(self, name: str) -> Any:
        return self._inputs.get(name)

    def set_inputs(self, data: dict) -> None:
        self._inputs.update(data)

    def set_config(self, config: dict) -> None:
        self._config.update(config)

    def set_output(self, name: str, value: str) -> None:
        self._outputs[name] = value

    def set_result(self, data: dict) -> None:
        """Set full output data (not just named outputs)."""
        self._outputs["_result"] = data

    def log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        line = f"[{ts}] {msg}"
        self._logs.append(line)
        print(line)  # Also to server console for now

    def set_raw_llm(self, raw: str) -> None:
        self._raw_llm = raw

    def set_meta(self, key: str, value: Any) -> None:
        self._meta[key] = value

    def add_log(self, line: str) -> None:
        """Add a log line from the handler for streaming."""
        ts = datetime.now(timezone.utc).isoformat()
        formatted = f"[{ts}] {line}"
        self._logs.append(formatted)
        print(formatted)

    @property
    def output_path(self) -> str | None:
        """Return primary output file path if set."""
        return self._meta.get("output_path")

    @property
    def logs(self) -> list[str]:
        return list(self._logs)

    # --- snapshot persistence ---

    def save_snapshot(self) -> Path:
        run_dir = RUNS_DIR / f"{self.node_type}_{self.run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        snapshot = {
            "run_id": self.run_id,
            "node_type": self.node_type,
            "workflow_id": self.workflow_id,
            "started_at": self._started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }

        (run_dir / "meta.json").write_text(
            json.dumps({**snapshot, **self._meta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "input.json").write_text(
            json.dumps(self._inputs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "config.json").write_text(
            json.dumps(self._config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "output.json").write_text(
            json.dumps(self._outputs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "logs.txt").write_text("\n".join(self._logs), encoding="utf-8")
        if self._raw_llm:
            (run_dir / "raw_llm.json").write_text(self._raw_llm, encoding="utf-8")

        return run_dir
