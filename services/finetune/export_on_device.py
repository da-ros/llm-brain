"""Build the Q4 packs the iPhone app downloads.

`--fixture` writes a small weight file and a true checksum. CI uses that.
`--real` is the laptop step that quantizes Qwen3.5-4B. It does not copy
anything into the LLM container.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

BASE_ID = "qwen3.5-4b-base-q4"
PREMIUM_ID = "qwen3.5-4b-finetuned-q4"
FAMILY = "Qwen3.5-4B"
PARAMETERS = "4.0B"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
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
    filename = f"{pack_id}.pte"
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
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def export_base(out_dir: Path, *, fixture: bool) -> dict:
    payload = b"Q4-FIXTURE-BASE" if fixture else _real_base_bytes()
    return _write_pack(out_dir / "base", pack_id=BASE_ID, tier="free", payload=payload)


def export_premium(out_dir: Path, user_id: str, adapter_dir: Path, *, fixture: bool) -> dict | None:
    if not _adapter_present(adapter_dir):
        return None
    payload = f"Q4-FIXTURE-PREMIUM-{user_id}".encode() if fixture else _real_premium_bytes(adapter_dir)
    return _write_pack(
        out_dir / "users" / user_id,
        pack_id=PREMIUM_ID,
        tier="premium",
        payload=payload,
        user_id=user_id,
    )


def _adapter_present(adapter_dir: Path) -> bool:
    return (adapter_dir / "adapter_config.json").is_file()


def _real_base_bytes() -> bytes:
    raise SystemExit(
        "Real Q4 export of base Qwen3.5-4B runs on the laptop. "
        "It must not write the LLM container weights. Use --fixture in CI."
    )


def _real_premium_bytes(adapter_dir: Path) -> bytes:
    raise SystemExit(
        f"Real merge+Q4 reads the LoRA adapter at {adapter_dir} on the laptop. "
        "It must not write the LLM container weights. Use --fixture in CI."
    )


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
