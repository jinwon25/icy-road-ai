"""Execute a notebook in a real Jupyter kernel without saving its outputs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import nbformat
from jupyter_client import KernelManager


def check_notebook(path: Path, timeout: int = 180, run_stages: list[str] | None = None) -> None:
    path = path.resolve()
    notebook = nbformat.read(path, as_version=4)
    nbformat.validate(notebook)
    kernel_name = notebook.metadata.get("kernelspec", {}).get("name", "python3")
    manager = KernelManager(kernel_name=kernel_name)
    environment = os.environ.copy()
    # 검증 커널의 설정·이력을 임시 폴더에 두어 사용자 프로필을 변경하지 않는다.
    runtime = tempfile.TemporaryDirectory(prefix='icy_road_notebook_')
    environment['IPYTHONDIR'] = str(Path(runtime.name) / 'ipython')
    environment['JUPYTER_RUNTIME_DIR'] = runtime.name
    manager.connection_file = str(Path(runtime.name) / 'kernel.json')
    if run_stages:
        environment["ICY_ROAD_RUN_STAGES"] = json.dumps(run_stages)
    manager.start_kernel(cwd=str(path.parent), env=environment)
    client = manager.client()
    client.start_channels()
    try:
        client.wait_for_ready(timeout=30)
        count = 0
        for index, cell in enumerate(notebook.cells, start=1):
            if cell.cell_type != "code":
                continue
            count += 1
            message_id = client.execute(cell.source, store_history=False)
            deadline = time.monotonic() + timeout
            error = None
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Cell {index} exceeded {timeout} seconds")
                message = client.get_iopub_msg(timeout=remaining)
                if message.get("parent_header", {}).get("msg_id") != message_id:
                    continue
                if message["msg_type"] == "error":
                    error = message["content"]
                if message["msg_type"] == "status" and message["content"]["execution_state"] == "idle":
                    break
            reply = client.get_shell_msg(timeout=max(1, deadline - time.monotonic()))
            if reply["content"]["status"] != "ok" or error:
                details = "\n".join(error.get("traceback", [])) if error else str(reply["content"])
                raise RuntimeError(f"Cell {index} failed:\n{details}")
            print(f"Cell {index}: OK")
        print(f"Notebook validated in Jupyter kernel: {count} code cells; outputs not saved")
    finally:
        client.stop_channels()
        manager.shutdown_kernel(now=True)
        runtime.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="notebooks/analysis_review.ipynb", type=Path)
    parser.add_argument("--timeout", type=int, default=180, help="Seconds allowed per code cell")
    parser.add_argument("--run-stage", action="append", default=[], help="Registered stage ID to run")
    args = parser.parse_args()
    try:
        check_notebook(args.path, args.timeout, args.run_stage)
    except Exception as exc:
        print(f"Notebook validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
