"""Builds the prebuilt compatibility code in src/compat."""

import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPAT = os.path.join(ROOT, "src", "compat")
TEMPLATE = os.path.join(ROOT, "deps", "BKRecompModTemplate")
DECOMP = os.path.join(TEMPLATE, "bk-decomp")
TOOLS = os.path.join(ROOT, "build", "deps")
EXE = ".exe" if os.name == "nt" else ""
CLANG = os.path.join(TOOLS, "llvm", "bin", "clang" + EXE)
LLD = os.path.join(TOOLS, "llvm", "bin", "ld.lld" + EXE)
MODTOOL = os.path.join(TOOLS, "bin", "RecompModTool" + EXE)
BUILD = os.path.join(ROOT, "build", "compat")

CFLAGS = [
    "-target", "mips", "-mips2", "-mabi=32", "-O2", "-G0", "-mno-abicalls", "-mno-odd-spreg",
    "-mno-check-zero-division", "-fomit-frame-pointer", "-ffast-math", "-fno-unsafe-math-optimizations",
    "-fno-builtin-memset", "-funsigned-char", "-fno-builtin-sinf", "-fno-builtin-cosf",
    "-Wall", "-Wextra", "-Wno-incompatible-library-redeclaration", "-Wno-unused-parameter",
    "-Wno-unknown-pragmas", "-Wno-unused-variable", "-Wno-missing-braces", "-Wno-unsupported-floating-point-opt",
    "-Werror=section", "-Wno-visibility",
    "-D_LANGUAGE_C", "-nostdinc", "-ffunction-sections",
    "-DMIPS", "-DF3DEX_GBI",
    "-I", os.path.join(TEMPLATE, "include"), "-I", os.path.join(TEMPLATE, "include", "dummy_headers"),
    "-I", os.path.join(DECOMP, "include"), "-I", os.path.join(DECOMP, "include", "2.0L"),
    "-I", os.path.join(DECOMP, "include", "2.0L", "PR"),
]

MOD_TOML = """[manifest]
id = "bkrecomp_romhack_compat"
version = "1.0.0"
display_name = "Romhack compat"
description = "Prebuilt compatibility code for converted romhacks."
short_description = "Prebuilt compatibility code"
authors = [ "BK Recomp Romhack Converter" ]
game_id = "bk"
minimum_recomp_version = "1.0.0"
dependencies = []
optional_dependencies = []
native_libraries = []

[inputs]
elf_path = "{elf}"
mod_filename = "compat"
func_reference_syms_file = "{syms}"
data_reference_syms_files = [ "{datasyms}" ]
additional_files = []
"""


def run(cmd):
    print(" ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)))
    subprocess.run(cmd, check=True)


def main():
    if not os.path.isdir(os.path.join(DECOMP, "include")):
        sys.exit("The submodules are missing. Run: git submodule update --init --recursive")
    for tool in (CLANG, LLD, MODTOOL):
        if not os.path.exists(tool):
            sys.exit(f"Missing {tool}. Run tools/build_deps.py --llvm first.")

    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(BUILD)

    objs = []
    for src in sorted(glob.glob(os.path.join(COMPAT, "*.c"))):
        obj = os.path.join(BUILD, os.path.basename(src)[:-2] + ".o")
        run([CLANG, *CFLAGS, "-c", src, "-o", obj])
        objs.append(obj)

    elf = os.path.join(BUILD, "mod.elf")
    run([LLD, *objs, "-nostdlib", "-T", os.path.join(TEMPLATE, "mod.ld"), "-Map", os.path.join(BUILD, "mod.map"),
         "--unresolved-symbols=ignore-all", "--emit-relocs", "-e", "0", "--no-nmagic", "-gc-sections", "-o", elf])

    syms = os.path.join(TEMPLATE, "BanjoRecompSyms")
    toml = os.path.join(BUILD, "mod.toml")
    with open(toml, "w") as file:
        file.write(MOD_TOML.format(elf=elf.replace("\\", "/"),
                                syms=os.path.join(syms, "bk.us.rev0.syms.toml").replace("\\", "/"),
                                datasyms=os.path.join(syms, "bk.us.rev0.datasyms.toml").replace("\\", "/")))
    run([MODTOOL, toml, BUILD])

    for name in ("mod_syms.bin", "mod_binary.bin"):
        shutil.copy(os.path.join(BUILD, name), os.path.join(COMPAT, name))
    print(f"Wrote {COMPAT}")


if __name__ == "__main__":
    main()
