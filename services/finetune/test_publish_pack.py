"""The iPhone pack merge writes the quantized file without calling llama.cpp."""

import json
from pathlib import Path


def test_merge_writes_the_quantized_file(tmp_path: Path, monkeypatch):
    import publish_pack

    dest = tmp_path / "pack" / "model.gguf"
    status = tmp_path / "pack" / "publish.json"
    tools = publish_pack.LlamaTools(
        convert=tmp_path / "convert.py",
        quantize=tmp_path / "quantize",
        source_root=tmp_path,
    )
    monkeypatch.setattr(publish_pack, "ensure_tools", lambda: tools)

    def merge_copy(_adapter: Path, dest: Path) -> None:
        dest.mkdir(parents=True)

    monkeypatch.setattr(publish_pack, "merge_adapter_into_copy", merge_copy)
    monkeypatch.setattr(publish_pack, "convert_hf", lambda *_args: None)

    def quantize(_tools, _merged: Path, outfile: Path) -> None:
        outfile.write_bytes(b"q4")

    monkeypatch.setattr(publish_pack, "quantize", quantize)
    publish_pack.merge_adapter_to_gguf(tmp_path / "adapter", dest, status)
    assert dest.read_bytes() == b"q4"
    assert json.loads(status.read_text(encoding="utf-8"))["phase"] == "quantizing"
    assert not (tmp_path / "pack" / ".publish-work").exists()
