"""Builds the tools in deps/ into build/deps/bin, and with --llvm fetches clang for the compatibility code."""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPS = os.path.join(ROOT, "deps")
OUT = os.path.join(ROOT, "build", "deps")
BIN = os.path.join(OUT, "bin")
LLVM_DIR = os.path.join(OUT, "llvm")
# 19.1.0 miscompiles MIPS (BKRecompModTemplate's README), so stay on 18.
LLVM_INSTALLER = "https://github.com/llvm/llvm-project/releases/download/llvmorg-18.1.8/LLVM-18.1.8-win64.exe"


def _vs_dev_cmd():
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                           "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if not os.path.isfile(vswhere):
        sys.exit("Visual Studio with the C++ tools is needed to build the tools.")
    path = subprocess.run([vswhere, "-latest", "-products", "*", "-requires",
                           "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return os.path.join(path, "Common7", "Tools", "VsDevCmd.bat")


def run(cmd):
    print(">", subprocess.list2cmdline(cmd))
    if os.name == "nt":
        dev = _vs_dev_cmd()
        subprocess.run(f'call "{dev}" -arch=x64 -host_arch=x64 >nul && {subprocess.list2cmdline(cmd)}',
                       shell=True, check=True)
    else:
        subprocess.run(cmd, check=True)


def build(name, *targets):
    build_dir = os.path.join(OUT, name)
    run(["cmake", "-S", os.path.join(DEPS, name), "-B", build_dir, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
         f"-DCMAKE_RUNTIME_OUTPUT_DIRECTORY={BIN}"])
    run(["cmake", "--build", build_dir, *(["--target", *targets] if targets else [])])


def fetch_llvm():
    seven_zip = shutil.which("7z") or r"C:\Program Files\7-Zip\7z.exe"
    if not os.path.isfile(seven_zip):
        sys.exit("7-Zip is needed to unpack the LLVM installer.")
    installer = os.path.join(OUT, os.path.basename(LLVM_INSTALLER))
    if not os.path.isfile(installer):
        print("Downloading", LLVM_INSTALLER)
        urllib.request.urlretrieve(LLVM_INSTALLER, installer)
    subprocess.run([seven_zip, "x", "-y", f"-o{LLVM_DIR}", installer, "bin/clang.exe", "bin/ld.lld.exe"],
                   check=True, stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llvm", action="store_true",
                        help="also fetch clang 18.1.8 (only the compatibility code needs it)")
    parser.add_argument("--merger-only", action="store_true",
                        help="only build RecompModMerger, the one tool the packaged converter bundles")
    args = parser.parse_args()

    if not os.path.isfile(os.path.join(DEPS, "N64Recomp", "CMakeLists.txt")):
        sys.exit("The submodules are missing. Run: git submodule update --init --recursive")
    if args.llvm and os.name != "nt":
        sys.exit("--llvm fetches LLVM's Windows installer. Elsewhere, put clang and ld.lld 18.1.8 "
                 "in build/deps/llvm/bin yourself.")
    os.makedirs(BIN, exist_ok=True)
    if args.merger_only:
        build("N64Recomp", "RecompModMerger")
    else:
        build("N64Recomp", "RecompModTool", "RecompModMerger")
        build("BKRecompRomhackTool")
    if args.llvm:
        fetch_llvm()
    print("Tools are in", BIN)


if __name__ == "__main__":
    main()
