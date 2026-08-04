from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

from careerflow.document_engine import apply_document, inspect_document


MAX_ARCHIVE_FILES = 2_000
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


def validate_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise ValueError("archive contains too many files")
        total = sum(info.file_size for info in infos)
        compressed = sum(max(info.compress_size, 1) for info in infos)
        if total > MAX_ARCHIVE_BYTES or total / compressed > MAX_COMPRESSION_RATIO:
            raise ValueError("archive expansion limit exceeded")
        for info in infos:
            normalized = Path(info.filename.replace("\\", "/"))
            if normalized.is_absolute() or ".." in normalized.parts:
                raise ValueError("archive contains an unsafe path")


def inspect(source: Path, output: Path) -> dict:
    if source.suffix.lower() == ".docx":
        validate_zip(source)
    template = output / "template"
    profile_path = inspect_document(source, template, "default")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    text = "\n".join(str(region.get("text", "")) for region in profile["regions"] if region.get("text"))
    if len(text.strip()) < 40:
        raise ValueError("document has no trustworthy text layer")
    for path in template.iterdir():
        if path.name.startswith("original"):
            continue
        shutil.copy2(path, output / path.name)
    (output / "extracted-text.txt").write_text(text + "\n", encoding="utf-8")
    return {
        "format": profile["format"],
        "region_count": len(profile["regions"]),
        "visual_qa_required": True,
    }


def build(package: Path, output: Path) -> dict:
    validate_zip(package)
    unpacked = output.parent / "input"
    unpacked.mkdir()
    with zipfile.ZipFile(package) as archive:
        archive.extractall(unpacked)
    profile = json.loads((unpacked / "document-profile.json").read_text(encoding="utf-8"))
    candidates = list(unpacked.glob("*.pdf")) + list(unpacked.glob("*.docx"))
    if len(candidates) != 1:
        raise ValueError("build package must contain exactly one source document")
    template = output.parent / "template"
    template.mkdir()
    shutil.copy2(candidates[0], template / profile["source_file"])
    shutil.copy2(unpacked / "document-profile.json", template / "document-profile.json")
    result_path = apply_document(template, unpacked / "document-plan.json", output)
    return json.loads(result_path.read_text(encoding="utf-8"))


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: runner <inspect|build> <source> <output-dir>")
    action, source_value, output_value = sys.argv[1:]
    source = Path(source_value).resolve()
    output = Path(output_value).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if action == "inspect":
        result = inspect(source, output)
    elif action == "build":
        result = build(source, output)
    else:
        raise ValueError("unsupported document action")
    (output / "worker-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

