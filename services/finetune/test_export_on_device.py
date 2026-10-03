"""On-device Q4 pack export. Fixture files only — no 4B download."""

import hashlib
import json
from pathlib import Path


def test_base_fixture_manifest_matches_file(tmp_path: Path):
    from export_on_device import export_base, pack_ready

    manifest = export_base(tmp_path, fixture=True)
    weight = tmp_path / "base" / manifest["filename"]
    assert manifest["id"] == "qwen3.5-4b-base-q4"
    assert manifest["family"] == "Qwen3.5-4B"
    assert manifest["tier"] == "free"
    assert manifest["quantization"] == "Q4"
    assert manifest["parameters"] == "4.0B"
    assert manifest["sha256"] == hashlib.sha256(weight.read_bytes()).hexdigest()
    assert pack_ready(tmp_path / "base")


def test_checksum_mismatch_is_not_ready(tmp_path: Path):
    from export_on_device import export_base, pack_ready
    export_base(tmp_path, fixture=True)
    manifest_path = tmp_path / "base" / "manifest.json"
    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    body["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(body), encoding="utf-8")
    assert pack_ready(tmp_path / "base") is False


def test_premium_fixture_includes_user_and_leaves_base(tmp_path: Path):
    from export_on_device import export_base, export_premium, pack_ready
    export_base(tmp_path, fixture=True)
    adapter = tmp_path / "adapters" / "user-a" / "adapter"
    adapter.mkdir(parents=True)
    (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
    manifest = export_premium(tmp_path, "user-a", adapter, fixture=True)
    assert manifest is not None
    assert manifest["id"] == "qwen3.5-4b-finetuned-q4"
    assert manifest["tier"] == "premium"
    assert manifest["user_id"] == "user-a"
    assert pack_ready(tmp_path / "users" / "user-a")
    assert pack_ready(tmp_path / "base")


def test_missing_adapter_writes_nothing(tmp_path: Path):
    from export_on_device import export_base, export_premium, pack_ready
    export_base(tmp_path, fixture=True)
    missing = tmp_path / "nope" / "adapter"
    assert export_premium(tmp_path, "user-b", missing, fixture=True) is None
    assert not (tmp_path / "users" / "user-b").exists()
    assert pack_ready(tmp_path / "base")


def test_real_flag_does_not_touch_a_container_dir(tmp_path: Path):
    from export_on_device import export_base
    container = tmp_path / "llm-container"
    container.mkdir()
    marker = container / "weights.bin"
    marker.write_bytes(b"base-weights")
    try:
        export_base(tmp_path / "out", fixture=False)
    except SystemExit as exc:
        assert "LLM container" in str(exc)
    else:
        raise AssertionError("real export should stop")
    assert marker.read_bytes() == b"base-weights"
    assert not (tmp_path / "out").exists()
