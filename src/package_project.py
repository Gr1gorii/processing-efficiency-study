"""Package verified research files with a per-file checksum manifest."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    files = [ROOT / name for name in ["README.md", "README.it.md", "requirements.txt",
                                      "config.proposed.json", "config.main.json", ".gitignore", "PUBLIC-MANIFEST.json"]]
    for directory in ["src", "tests", "data", "results", "charts", "docs", "reports"]:
        files.extend(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    files = sorted(files)
    manifest = {str(path.relative_to(ROOT)): {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size
    } for path in files}
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    archive_path = destination / "processing-efficiency-study.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, "processing-efficiency-study/" + str(path.relative_to(ROOT)))
        archive.writestr("processing-efficiency-study/MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for name, entry in manifest.items():
            data = archive.read("processing-efficiency-study/" + name)
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    receipt = {"archive": str(archive_path.relative_to(ROOT)), "source_files": len(files),
               "bytes": archive_path.stat().st_size,
               "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
               "all_archived_file_hashes_verified": True}
    (destination / "archive-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
