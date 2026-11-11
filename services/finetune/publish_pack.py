"""Merge a LoRA adapter into the Q4 GGUF the iPhone downloads.

The converter and the Mac build of llama.cpp are stored under data/llama.cpp
the first time a pack is published. The base Q4 file is stored under
data/models/base. Neither path is the model the cloud chat process loaded.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tarfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

LLAMA_TAG = "b12292"
BIN_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/"
    f"{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-macos-arm64.tar.gz"
)
SRC_URL = f"https://github.com/ggml-org/llama.cpp/archive/refs/tags/{LLAMA_TAG}.tar.gz"

_lock = threading.Lock()
_active: set[str] = set()


@dataclass(frozen=True)
class LlamaTools:
    convert: Path
    export_lora: Path
    quantize: Path
    source_root: Path


def repo_data() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def write_status(path: Path, status: str, phase: str, error: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"status": status, "phase": phase, "error": error}),
        encoding="utf-8",
    )


def pack_root() -> Path:
    from config import get_settings

    raw = (get_settings().ONDEVICE_MODEL_DIR or "").strip()
    if raw:
        return Path(raw)
    return repo_data() / "on-device"


def start_publish(user_id: str, adapter_dir: Path) -> None:
    """Publish one account's adapter. A second publish waits until this one finishes."""
    with _lock:
        if _active:
            raise RuntimeError("A pack is already being published.")
        _active.add(user_id)
    thread = threading.Thread(
        target=_publish,
        args=(user_id, adapter_dir),
        name=f"publish-{user_id}",
        daemon=False,
    )
    thread.start()


def _publish(user_id: str, adapter_dir: Path) -> None:
    from export_on_device import export_premium
    from logging_setup import logger

    status_path = pack_root() / "users" / user_id / "publish.json"
    try:
        write_status(status_path, "running", "preparing")
        written = export_premium(pack_root(), user_id, adapter_dir, fixture=False)
        if written is None:
            write_status(status_path, "failed", "preparing", "No adapter yet.")
            return
        write_status(status_path, "completed", "completed")
        logger.info("Published on-device pack for %s", user_id)
    except Exception as exc:
        logger.exception("On-device pack failed for %s", user_id)
        write_status(status_path, "failed", "failed", str(exc)[:800])
    finally:
        with _lock:
            _active.discard(user_id)


def merge_adapter_to_gguf(adapter_dir: Path, dest: Path, status_path: Path) -> None:
    """Convert the PEFT adapter, merge it into the base GGUF, and quantize to Q4."""
    write_status(status_path, "running", "tools")
    tools = ensure_tools()
    write_status(status_path, "running", "base")
    base = ensure_base_gguf()
    work = dest.parent / ".publish-work"
    work.mkdir(parents=True, exist_ok=True)
    lora_gguf = work / "adapter-f16.gguf"
    merged = work / "merged-f16.gguf"
    partial = dest.with_name(dest.name + ".partial")
    try:
        write_status(status_path, "running", "converting")
        convert_lora(tools, adapter_dir, lora_gguf)
        write_status(status_path, "running", "merging")
        export_lora(tools, base, lora_gguf, merged)
        write_status(status_path, "running", "quantizing")
        quantize(tools, merged, partial)
        partial.replace(dest)
    finally:
        partial.unlink(missing_ok=True)
        lora_gguf.unlink(missing_ok=True)
        merged.unlink(missing_ok=True)
        if work.exists() and not any(work.iterdir()):
            work.rmdir()


def ensure_tools() -> LlamaTools:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Publishing the iPhone pack runs on this Mac.")
    root = repo_data() / "llama.cpp" / LLAMA_TAG
    source = root / "source"
    binary = root / "bin"
    convert = _find_optional(source, "convert_lora_to_gguf.py")
    export_bin = _find_optional(binary, "llama-export-lora")
    quantize_bin = _find_optional(binary, "llama-quantize")
    if convert is None:
        archive = root / "source.tar.gz"
        _download(SRC_URL, archive)
        _extract(archive, source)
        convert = _require(source, "convert_lora_to_gguf.py")
    if export_bin is None or quantize_bin is None:
        archive = root / "macos-arm64.tar.gz"
        _download(BIN_URL, archive)
        _extract(archive, binary)
        export_bin = _require(binary, "llama-export-lora")
        quantize_bin = _require(binary, "llama-quantize")
    export_bin.chmod(export_bin.stat().st_mode | 0o111)
    quantize_bin.chmod(quantize_bin.stat().st_mode | 0o111)
    return LlamaTools(
        convert=convert,
        export_lora=export_bin,
        quantize=quantize_bin,
        source_root=convert.parent,
    )


def ensure_base_gguf() -> Path:
    dest = repo_data() / "models" / "base" / "Qwen3.5-4B-Q4_K_M.gguf"
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return dest
    from export_on_device import _fetch_base_gguf

    _fetch_base_gguf(dest)
    return dest


def convert_lora(tools: LlamaTools, adapter_dir: Path, outfile: Path) -> None:
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env.setdefault("HF_HOME", str(repo_data() / "huggingface"))
    _run(
        [
            sys.executable,
            str(tools.convert),
            "--base",
            str(_hf_snapshot(env["HF_HOME"])),
            "--outfile",
            str(outfile),
            "--outtype",
            "f16",
            str(adapter_dir),
        ],
        cwd=tools.source_root,
        env=env,
    )


def export_lora(tools: LlamaTools, base: Path, lora: Path, outfile: Path) -> None:
    _run(
        [str(tools.export_lora), "-m", str(base), "--lora", str(lora), "-o", str(outfile)],
    )


def quantize(tools: LlamaTools, merged: Path, outfile: Path) -> None:
    _run([str(tools.quantize), str(merged), str(outfile), "Q4_K_M"])


def _hf_snapshot(hf_home: str) -> Path:
    snapshots = Path(hf_home) / "hub" / "models--Qwen--Qwen3.5-4B" / "snapshots"
    if snapshots.is_dir():
        found = [path for path in snapshots.iterdir() if (path / "config.json").is_file()]
        if found:
            return found[0]
    raise RuntimeError("The local Qwen3.5-4B config was not found under data/huggingface.")


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    urllib.request.urlretrieve(url, partial)
    partial.replace(dest)


def _extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as handle:
        handle.extractall(dest, filter="data")


def _find_optional(root: Path, name: str) -> Path | None:
    if not root.exists():
        return None
    matches = [path for path in root.rglob(name) if path.is_file()]
    return matches[0] if matches else None


def _require(root: Path, name: str) -> Path:
    found = _find_optional(root, name)
    if found is None:
        raise RuntimeError(f"{name} was not in {root}")
    return found


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        tail = detail[-800:] if detail else f"{Path(cmd[0]).name} failed"
        raise RuntimeError(tail)
