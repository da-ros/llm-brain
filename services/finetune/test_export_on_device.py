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


def test_premium_real_writes_the_merged_file_and_manifest(tmp_path: Path, monkeypatch):
    from export_on_device import export_premium, pack_ready

    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")

    def fake_merge(adapter_dir: Path, dest: Path, status_path: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"Q4-MERGED")
        status_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("publish_pack.merge_adapter_to_gguf", fake_merge)
    manifest = export_premium(tmp_path, "user-a", adapter, fixture=False)
    assert manifest is not None
    weight = tmp_path / "users" / "user-a" / manifest["filename"]
    assert weight.read_bytes() == b"Q4-MERGED"
    assert manifest["id"] == "qwen3.5-4b-finetuned-q4"
    assert manifest["user_id"] == "user-a"
    assert pack_ready(tmp_path / "users" / "user-a")


def test_latest_completed_log_sets_the_pack_tag(tmp_path: Path, monkeypatch):
    from export_on_device import _manifest, installed_tag

    logs = tmp_path / "training_logs"
    logs.mkdir()
    (logs / "ft-job-old.md").write_text(
        "- **user_id**: user-a\n"
        "- **model_version**: qwen3.5-4b-lora-v1\n"
        "- **completed_at**: 2026-11-12T00:00:00+00:00\n",
        encoding="utf-8",
    )
    (logs / "ft-job-new.md").write_text(
        "- **user_id**: user-a\n"
        "- **model_version**: qwen3.5-4b-lora-v5\n"
        "- **completed_at**: 2026-11-16T21:43:47+00:00\n",
        encoding="utf-8",
    )
    (logs / "ft-job-other.md").write_text(
        "- **user_id**: someone-else\n"
        "- **model_version**: qwen3.5-4b-lora-v9\n"
        "- **completed_at**: 2026-11-17T00:00:00+00:00\n",
        encoding="utf-8",
    )
    assert installed_tag("user-a", logs) == "qwen3.5-4b-lora-v5"
    monkeypatch.setattr(
        "export_on_device.installed_tag", lambda user_id, log_dir=None: installed_tag(user_id, logs)
    )
    weight = tmp_path / "pack.gguf"
    weight.write_bytes(b"Q4")
    manifest = _manifest(
        tmp_path,
        weight,
        pack_id="qwen3.5-4b-finetuned-q4",
        tier="premium",
        user_id="user-a",
    )
    assert manifest["tag"] == "qwen3.5-4b-lora-v5"


def test_missing_adapter_writes_nothing(tmp_path: Path):
    from export_on_device import export_base, export_premium, pack_ready

    export_base(tmp_path, fixture=True)
    missing = tmp_path / "nope" / "adapter"
    assert export_premium(tmp_path, "user-b", missing, fixture=True) is None
    assert not (tmp_path / "users" / "user-b").exists()
    assert pack_ready(tmp_path / "base")


def test_real_flag_does_not_touch_a_container_dir(tmp_path: Path, monkeypatch):
    from export_on_device import export_base, pack_ready

    container = tmp_path / "llm-container"
    container.mkdir()
    marker = container / "weights.bin"
    marker.write_bytes(b"base-weights")

    def fake_fetch(dest):
        assert "llm-container" not in dest.parts
        dest.write_bytes(b"Q4-GGUF")

    monkeypatch.setattr("export_on_device._fetch_base_gguf", fake_fetch)
    manifest = export_base(tmp_path / "out", fixture=False)
    assert manifest["filename"].endswith(".gguf")
    assert pack_ready(tmp_path / "out" / "base")
    assert marker.read_bytes() == b"base-weights"
    assert not (container / "qwen3.5-4b-base-q4.gguf").exists()
