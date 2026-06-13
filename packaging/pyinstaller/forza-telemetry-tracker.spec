# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path.cwd()
FRONTEND_DIST = ROOT / "web" / "telemetry-tracker" / "dist"
TRACKER_RESOURCES = ROOT / "telemetry_tracker" / "resources"
MAP_CONVERTER_PUBLISH = ROOT / "build" / "map-converter" / "win-x64"
LICENSES_DIR = ROOT / "licenses"
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
RELEASE_METADATA = ROOT / "build" / "release-metadata.json"

def tree_entries(source: Path, target: str):
    if not source.exists():
        return []
    return [(str(path), str(Path(target) / path.relative_to(source).parent)) for path in source.rglob("*") if path.is_file()]

datas = []
datas += tree_entries(FRONTEND_DIST, "frontend-dist")
datas += tree_entries(TRACKER_RESOURCES, "resources")
datas += tree_entries(MAP_CONVERTER_PUBLISH, "bin/map-converter")
datas += tree_entries(LICENSES_DIR, "licenses")
if NOTICES.exists():
    datas.append((str(NOTICES), "."))
if RELEASE_METADATA.exists():
    datas.append((str(RELEASE_METADATA), "."))

a = Analysis(
    [str(ROOT / "telemetry_tracker" / "desktop_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["python_multipart", "uvicorn", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.lifespan.on", "anyio._backends._asyncio", "httpx._transports.default"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ForzaTelemetryTracker", debug=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name="ForzaTelemetryTracker")
