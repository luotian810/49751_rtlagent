"""打包可复现的 Windows 开发工程，保留源码、运行报告和便携 Icarus。"""
from pathlib import Path
import argparse
import re
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT.parent / "readable-rtl-agent-windows.zip"
OMIT_DIRECTORIES = {"__pycache__", ".git", ".venv", "venv", "downloads", "xsim.dir", ".Xil", "out", "outputs"}
OMIT_SUFFIXES = {".pyc", ".lic", ".key", ".pem", ".dmp", ".zip", ".out"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DESTINATION)
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part in OMIT_DIRECTORIES or part.startswith(".Xil_") for part in relative.parts):
            continue
        if not path.is_file() or path.suffix.lower() in OMIT_SUFFIXES:
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        # 一次性调试器脚本含特定安装版本的断点地址，不属于可运行交付入口。
        if relative.parts[0] == "runs" and path.suffix.lower() == ".py":
            continue
        # 不打印疑似凭据，仅报告文件位置，防止把 Key 带入交付包。
        if path.suffix.lower() in {".py", ".ps1", ".sh", ".md", ".json", ".jsonl", ".log", ".txt"}:
            if re.search(rb"\bsk-[A-Za-z0-9_-]{24,}", path.read_bytes()):
                raise RuntimeError(f"Possible API credential; package stopped: {relative}")
        files.append((path, relative))
    with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for path, relative in files:
            archive.write(path, Path(ROOT.name) / relative)
    with ZipFile(destination) as archive:
        damaged = archive.testzip()
        if damaged:
            raise RuntimeError(f"ZIP verification failed: {damaged}")
    print(f"{destination}\n{len(files)} files; {destination.stat().st_size / 1024**2:.2f} MiB; ZIP verified")


if __name__ == "__main__":
    main()
