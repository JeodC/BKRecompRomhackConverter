"""Packages the converter as a windowed executable (an .app on macOS) in build/dist/."""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
BUILD = os.path.join(ROOT, "build")
EXE = ".exe" if os.name == "nt" else ""
MERGER = os.path.join(BUILD, "deps", "bin", "RecompModMerger" + EXE)
SYMS = os.path.join(ROOT, "deps", "BKRecompModTemplate", "BanjoRecompSyms")
SEP = os.pathsep


def main():
    if not os.path.isfile(MERGER):
        sys.exit("RecompModMerger isn't built yet. Run tools/build_deps.py first.")

    mode = "--onedir" if sys.platform == "darwin" else "--onefile"
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", mode, "--windowed",
        "--name", "BKRecompRomhackConverter", "--paths", SRC,
        "--distpath", os.path.join(BUILD, "dist"), "--workpath", os.path.join(BUILD, "pyinstaller"),
        "--specpath", os.path.join(BUILD, "pyinstaller"),
        "--add-data", f"{os.path.join(SRC, 'compat', 'mod_binary.bin')}{SEP}compat",
        "--add-data", f"{os.path.join(SRC, 'compat', 'mod_syms.bin')}{SEP}compat",
        "--add-data", f"{os.path.join(SYMS, 'bk.us.rev0.syms.toml')}{SEP}BanjoRecompSyms",
        "--add-data", f"{os.path.join(SYMS, 'LICENSE')}{SEP}BanjoRecompSyms",
        "--add-binary", f"{MERGER}{SEP}bin",
        "--add-data", f"{os.path.join(ROOT, 'deps', 'N64Recomp', 'LICENSE')}{SEP}bin/N64Recomp",
        os.path.join(SRC, "__main__.py"),
    ], check=True, cwd=ROOT)
    print(os.path.join(BUILD, "dist", "BKRecompRomhackConverter" + (".app" if sys.platform == "darwin" else EXE)))


if __name__ == "__main__":
    main()
