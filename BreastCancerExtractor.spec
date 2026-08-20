from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata, is_module_or_submodule


root = Path(SPECPATH)
datas = [
    (str(root / "app" / "static"), "app/static"),
    (str(root / "knowledge"), "knowledge"),
]
binaries = []
hiddenimports = ["app.main", "ocr.service", "tkinter", "tkinter.ttk"]


def paddle_submodule_filter(name):
    return not is_module_or_submodule(name, "paddle.jit.sot")


for package in ("paddle", "paddleocr", "paddlex"):
    if package == "paddle":
        package_datas, package_binaries, package_hidden = collect_all(
            package,
            filter_submodules=paddle_submodule_filter,
        )
    else:
        package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# PaddleX checks its lightweight OCR dependencies through importlib.metadata at
# runtime. PyInstaller collects their modules, but not every distribution's
# metadata, so the frozen app would otherwise report that OCR is unavailable.
for distribution in (
    "imagesize",
    "opencv-contrib-python",
    "pyclipper",
    "pypdfium2",
    "python-bidi",
    "shapely",
):
    datas += copy_metadata(distribution)

a = Analysis(
    [str(root / "app" / "native_entry.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "ruff", "paddle.jit.sot"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BreastCancerExtractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BreastCancerExtractor",
)
