"""One-time workspace-local runtime download from official MSYS2 packages."""
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import urllib.request

root = Path(__file__).resolve().parents[1] / ".tools" / "iverilog"
root.mkdir(parents=True, exist_ok=True)
downloads = root / "downloads"
downloads.mkdir(exist_ok=True)
# URLs and checksums read from packages.msys2.org on 2026-09-28.
packages = [
    ("iverilog", "1~13.0-2", "e22c86dad1a0658d5f769362bfbec6533028c0d0bb63059b4fda0cc1084d1406"),
    ("bzip2", "1.0.8-4", "123768f30ae14ba654a6feb70f8526146a331bc85f831a91a549ffb3f6cbffc7"),
    ("readline", "8.3.003-1", "b943d7e2a61ac6e0304eac11cdcee15370a8c2ccee5b84487f8ad6c1e103d66c"),
    ("zlib", "1.3.2-2", "9e75842a070ba648e986e12424e1c92c9d7d77200e85f6a34eeb600819f2e694"),
    ("termcap", "1.3.1-7", "04ca275febc3ef461d55f8468fd05c6355ca0fda3be4a77bfdb906cf9d88a1e8"),
    ("libgcc", "16.2.0-4", "d615f6a8536ca16b1f049daea1fa440a3b7a405449ec0e93ad6106db43682d54"),
    ("libstdc++", "16.2.0-4", "3d4c3faf4c2c5c7a851ff12214ddcbf8c0d6df0964fc1d3ebd8c38f227183034"),
    ("libwinpthread", "14.0.0.r426.g4564ee4b5-1", "543017ce2731292b215bf1d36fd70a86d8a8d5ed0afba9d3db9fff89804cda71"),
]
provenance = []
for package, version, expected in packages:
    metadata_url = "https://packages.msys2.org/packages/mingw-w64-x86_64-" + package
    url = "https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-" + package.replace("+", "%2B") + "-" + version + "-any.pkg.tar.zst"
    target = downloads / (package.replace("+", "p") + ".pkg.tar.zst")
    if not target.exists():
        urllib.request.urlretrieve(url, target)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(f"SHA256 mismatch for {package}")
    members = subprocess.check_output(["tar", "-tf", str(target)], text=True).splitlines()
    if any(".." in Path(name).parts or name.startswith(("/", "\\")) for name in members):
        raise RuntimeError("unsafe archive member")
    subprocess.run(["tar", "-xf", str(target), "-C", str(root), "--strip-components", "1", "mingw64"], check=True)
    provenance.append(dict(package=package, source=metadata_url, download=url, sha256=actual))
    print(package, "installed", flush=True)
    (root / "packages.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

# Internal compiler processes also need the adjacent runtime DLLs on Windows.
for dll in (root / "bin").glob("*.dll"):
    shutil.copy2(dll, root / "lib" / "ivl" / dll.name)
print("Portable Icarus and runtime DLLs are ready.")
