"""Build the Q4 GGUF packs the iPhone app downloads.

The phone runs them with llama.cpp on the GPU (Metal). `--fixture` writes a
small weight file and a true checksum. CI uses that. `--real` for the base
pack downloads the published Q4 GGUF. `--real` for a premium pack merges that
user's LoRA adapter into the base model and quantizes it to Q4. Neither path
copies anything into the LLM container.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE_GGUF_URL = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf"

BASE_ID = "qwen3.5-4b-base-q4"
PREMIUM_ID = "qwen3.5-4b-finetuned-q4"
FAMILY = "Qwen3.5-4B"
PARAMETERS = "4.0B"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pack_ready(directory: Path) -> bool:
    """A pack is ready only when manifest sha256 matches the weight file."""
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filename = manifest.get("filename") or ""
    weight = directory / filename if filename else None
    if weight is None or not weight.is_file():
        return False
    return sha256_file(weight) == str(manifest.get("sha256") or "")


def _write_pack(
    directory: Path,
    *,
    pack_id: str,
    tier: str,
    payload: bytes,
    user_id: str | None = None,
) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{pack_id}.gguf"
    weight = directory / filename
    weight.write_bytes(payload)
    manifest = {
        "id": pack_id,
        "family": FAMILY,
        "tier": tier,
        "quantization": "Q4",
        "parameters": PARAMETERS,
        "filename": filename,
        "bytes": weight.stat().st_size,
        "sha256": sha256_file(weight),
    }
    if user_id is not None:
        manifest["user_id"] = user_id
        tag = installed_tag(user_id)
        if tag:
            manifest["tag"] = tag
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def installed_tag(user_id: str, log_dir: Path | None = None) -> str:
    """The newest completed fine-tune tag for this account, such as qwen3.5-4b-lora-v5."""
    directory = log_dir if log_dir is not None else Path(__file__).resolve().parents[2] / "data" / "training_logs"
    if not user_id or not directory.is_dir():
        return ""
    best_at = ""
    best = ""
    for path in directory.glob("ft-job-*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _log_field(text, "user_id") != user_id:
            continue
        version = _log_field(text, "model_version")
        completed = _log_field(text, "completed_at")
        if version and completed >= best_at:
            best_at = completed
            best = version
    return best


def _log_field(text: str, name: str) -> str:
    match = re.search(rf"^- \*\*{re.escape(name)}\*\*: (.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _fetch_base_gguf(dest: Path) -> None:
    """Stream the published Q4 GGUF. The caller chooses a path outside the LLM container."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    urllib.request.urlretrieve(BASE_GGUF_URL, partial)
    partial.replace(dest)


def export_base(out_dir: Path, *, fixture: bool) -> dict:
    if fixture:
        return _write_pack(
            out_dir / "base", pack_id=BASE_ID, tier="free", payload=b"Q4-FIXTURE-BASE"
        )
    directory = out_dir / "base"
    directory.mkdir(parents=True, exist_ok=True)
    weight = directory / f"{BASE_ID}.gguf"
    _fetch_base_gguf(weight)
    manifest = {
        "id": BASE_ID,
        "family": FAMILY,
        "tier": "free",
        "quantization": "Q4",
        "parameters": PARAMETERS,
        "filename": weight.name,
        "bytes": weight.stat().st_size,
        "sha256": sha256_file(weight),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def export_premium(out_dir: Path, user_id: str, adapter_dir: Path, *, fixture: bool) -> dict | None:
    if not _adapter_present(adapter_dir):
        return None
    directory = out_dir / "users" / user_id
    if fixture:
        return _write_pack(
            directory,
            pack_id=PREMIUM_ID,
            tier="premium",
            payload=f"Q4-FIXTURE-PREMIUM-{user_id}".encode(),
            user_id=user_id,
        )
    directory.mkdir(parents=True, exist_ok=True)
    weight = directory / f"{PREMIUM_ID}.gguf"
    from publish_pack import merge_adapter_to_gguf

    merge_adapter_to_gguf(adapter_dir, weight, directory / "publish.json")
    return _manifest(directory, weight, pack_id=PREMIUM_ID, tier="premium", user_id=user_id)


def _manifest(
    directory: Path,
    weight: Path,
    *,
    pack_id: str,
    tier: str,
    user_id: str | None = None,
) -> dict:
    manifest = {
        "id": pack_id,
        "family": FAMILY,
        "tier": tier,
        "quantization": "Q4",
        "parameters": PARAMETERS,
        "filename": weight.name,
        "bytes": weight.stat().st_size,
        "sha256": sha256_file(weight),
    }
    if user_id is not None:
        manifest["user_id"] = user_id
        tag = installed_tag(user_id)
        if tag:
            manifest["tag"] = tag
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _adapter_present(adapter_dir: Path) -> bool:
    return (adapter_dir / "adapter_config.json").is_file()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export on-device Q4 packs")
    parser.add_argument("kind", choices=("base", "premium"))
    parser.add_argument("--out", type=Path, default=Path("models/on-device"))
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--user-id", default="")
    parser.add_argument("--adapter-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.fixture == args.real:
        parser.error("pass exactly one of --fixture or --real")
    if args.kind == "base":
        export_base(args.out, fixture=args.fixture)
        return 0
    if not args.user_id:
        parser.error("premium requires --user-id")
    adapter = args.adapter_dir or Path("data/models") / args.user_id / "adapter"
    written = export_premium(args.out, args.user_id, adapter, fixture=args.fixture)
    if written is None:
        print(f"no adapter at {adapter}; base pack left unchanged", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
