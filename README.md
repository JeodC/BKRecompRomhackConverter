# BK Recomp Romhack Converter

Converts Banjo's Backpack romhacks into game-mode mods (`.nrm`) for [Banjo: Recompiled](https://github.com/BanjoRecomp/BanjoRecomp), plus a Thunderstore package. If you want to port a romhack, read [GUIDE.md](GUIDE.md) instead--this file covers working on the converter itself.

The converter automates what Wiseguy did for the Jiggies of Time and Nostalgia 64 recomp mods ([JiggiesOfTimeRecomp](https://github.com/Mr-Wiseguy/JiggiesOfTimeRecomp), [Nostalgia64Recomp](https://github.com/Mr-Wiseguy/Nostalgia64Recomp)).

## How it works

The romhack's `.bps` is applied to the vanilla ROM. If the modder supplies a patched ROM instead, a `.bps` is made from it. The patch goes into the `.nrm` as `patch.bps`, and Banjo: Recompiled applies it to the player's ROM at load time.

Banjo's Backpack "globalizes" the 13 level overlays: it decompresses and relocates them into one code block that the patched boot code DMAs to expansion RAM. In every romhack I've seen, that's ROM `0x3F00000` to RAM `0x80400000`. `src/codeblock.py` reads the block's addresses and size from that DMA call, finds each vanilla overlay inside it by masked instruction matching, and relocates the overlay's functions using Banjo: Recompiled's vanilla symbols. It also picks up functions the romhack's author wrote into spare space, by following `jal`s, and actor-table pointers that land on a stack-frame prologue. The result is the symbol file [BKRecompRomhackTool](https://github.com/Mr-Wiseguy/BKRecompRomhackTool) needs to recompile the changed vanilla functions and the code block into a mod binary.

Every converted romhack also gets the small prebuilt mod in `src/compat/`. It gives the romhack its own save file, sets up note saving, hides chosen actors while note saving is on, and resets texture palette state after each model draw. The converter fills in its `BKRCCFG1` config block rather than compiling it per romhack.

`src/notecount.py` counts static notes by parsing each map's setup file (the game's setup loader, plus the slot loader Banjo: Recompiled patches for note saving), and estimates bundle notes from note-dropping huts and placed note actors. Per-world totals are checked against note saving's 256-note limit.

RecompModMerger then combines the compatibility code with the recompiled romhack code. That's zipped with `mod.json`, `patch.bps` and the thumbnail into the `.nrm`, and the Thunderstore zip wraps the `.nrm`.

## Validation

With the patch from Wiseguy's 1.0.1 Jiggies of Time `.nrm`, the generated symbol file matches his exactly, function sizes included. For Nostalgia 64, every function start matches his symbol file, including the functions written into spare space--two sizes differ only by trailing zero padding.

Note counts match the table built into Banjo: Recompiled on every vanilla map, and the counts in the Jiggies of Time and Nostalgia 64 recomp mods.

## Development setup

The converter is Python 3.12 and only uses the standard library. Dependencies are submodules in `deps/`, and everything built goes to `build/`, which is gitignored.

```bash
git submodule update --init --recursive
python tools/build_deps.py          # RecompModTool, RecompModMerger and BKRecompRomhackTool into build/deps/bin
python tools/build_deps.py --llvm   # also clang 18.1.8, only needed for the compatibility code
```

`build_deps.py` needs CMake, Ninja and, on Windows, Visual Studio's C++ tools. `--llvm` only works on Windows, and needs 7-Zip to unpack the LLVM installer.

- `python src`: runs the converter. With no arguments, or a project file, it opens the window. `convert`, `count-notes` and `syms` are the command-line equivalents.
- `python tools/build_compat.py`: rebuilds the two `.bin` files in `src/compat/`. Only needed when `romhack_compat.c` changes.
- `python tools/build_exe.py`: packages `build/dist/BKRecompRomhackConverter.exe` (an `.app` on macOS) with PyInstaller, bundling RecompModMerger and the vanilla symbols.

## Not supported yet

Modders get the short version in [GUIDE.md](GUIDE.md#limitations). For whoever adds support:

- Compressed or multiple code blocks (Cut-Throat Coast, The Gruntch, Snow Glow Village and others).
- Romhacks that resize vanilla functions: BKRecompRomhackTool only detects edits made in place.
