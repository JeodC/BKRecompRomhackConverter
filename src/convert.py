"""Turns a Banjo-Kazooie romhack into a Banjo: Recompiled mod."""

import os
import subprocess
import tempfile
import zlib

import bkrom, bps, codeblock, compat_config, mod_files, notecount

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXE = ".exe" if os.name == "nt" else ""


def _bundled_or_checkout(bundled, checkout):
    """The copy inside the packaged converter, or the one in a source checkout"""
    return bundled if os.path.isfile(bundled) else checkout


VANILLA_SYMS = _bundled_or_checkout(
    os.path.join(HERE, "BanjoRecompSyms", "bk.us.rev0.syms.toml"),
    os.path.join(ROOT, "deps", "BKRecompModTemplate", "BanjoRecompSyms", "bk.us.rev0.syms.toml"))

SAVED_LEVELS = {1: "Mumbo's Mountain", 2: "Treasure Trove Cove", 3: "Clanker's Cavern", 4: "Bubblegloop Swamp",
                5: "Freezeezy Peak", 7: "Gobi's Valley", 8: "Click Clock Wood", 9: "Rusty Bucket Bay",
                0xA: "Mad Monster Mansion"}
MAX_NOTES_PER_LEVEL = 256


class ConvertError(Exception):
    pass


def find_merger():
    path = _bundled_or_checkout(os.path.join(HERE, "bin", "RecompModMerger" + EXE),
                                os.path.join(ROOT, "build", "deps", "bin", "RecompModMerger" + EXE))
    if not os.path.isfile(path):
        raise ConvertError("RecompModMerger is missing from the converter install.")
    return path


def load_romhack(vanilla, path, log):
    """(romhack ROM, BPS patch against the vanilla .z64)"""
    with open(path, "rb") as file:
        data = file.read()

    if data[:4] == bps.MAGIC:
        wanted = bps.source_crc(data)
        for order, source in (("z64", vanilla), ("v64", bkrom.swap16(vanilla)), ("n64", bkrom.swap32(vanilla))):
            if zlib.crc32(source) == wanted:
                romhack = bkrom.to_z64(bps.apply(source, data))
                if order == "z64":
                    return romhack, data
                log(f"The patch was made against a .{order} ROM; rebuilding it for .z64.")
                return romhack, bps.create(vanilla, romhack)
        raise ConvertError("This patch was made from a different ROM. Remake it from Banjo-Kazooie "
                           "NTSC-U 1.0 (Rev 0).")

    try:
        romhack = bkrom.to_z64(data)
    except bkrom.RomError:
        raise ConvertError("The romhack file is neither a .bps patch nor an N64 ROM.")
    if bkrom.sha1(romhack) == bkrom.VANILLA_SHA1:
        raise ConvertError("That's the unmodified game, not a romhack.")
    log("Creating a BPS patch from the patched ROM.")
    return romhack, bps.create(vanilla, romhack)


def check_note_counts(romhack, note_counts, log):
    levels = notecount.map_levels(romhack)
    if not levels:
        log("Warning: couldn't read which level each map belongs to, so per-world note limits weren't checked.")
        return
    totals = {}
    for map_id, (static, bundle) in note_counts.items():
        level = levels.get(map_id, 0)
        totals[level] = totals.get(level, 0) + static + bundle
    too_many = [f"{SAVED_LEVELS[level]} slot (level {level:#x}): {total}" for level, total in sorted(totals.items())
                if level in SAVED_LEVELS and total > MAX_NOTES_PER_LEVEL]
    if too_many:
        raise ConvertError(f"Note saving can track at most {MAX_NOTES_PER_LEVEL} notes per world, and these have "
                           "more:\n" + "\n".join(too_many) + "\nTurn note saving off on the Notes tab.")
    untracked = sum(total for level, total in totals.items() if level not in SAVED_LEVELS)
    if untracked:
        log(f"{untracked} notes are outside the nine worlds, so note saving won't remember them.")


def _run_tool(cmd, cwd, log):
    log("> " + " ".join(os.path.basename(arg) for arg in cmd))
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, creationflags=flags)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-15:])
        raise ConvertError(f"{os.path.basename(cmd[0])} failed:\n{tail}")
    return result.stdout


def run(project, log=print):
    """Builds the .nrm and Thunderstore zip, returning their paths"""
    problems = []
    if not project.vanilla_rom:
        problems.append("Files: Choose the Banjo-Kazooie ROM.")
    if not project.romhack:
        problems.append("Files: Choose the romhack.")
    if not os.path.isfile(project.romhack_tool or ""):
        problems.append("Files: Choose BKRecompRomhackTool.")
    if not project.output_dir:
        problems.append("Files: Choose an output folder.")
    problems += ["Mod info: " + problem for problem in mod_files.check_mod(project.mod, project.thumbnail_path())]
    thunderstore_problems = mod_files.check_thunderstore(project.thunderstore) if project.make_thunderstore else []
    problems += ["Thunderstore: " + problem for problem in thunderstore_problems]
    if problems:
        hint = "\n\nOr untick Make a Thunderstore package to build only the .nrm." if thunderstore_problems else ""
        raise ConvertError("Fix these first:\n- " + "\n- ".join(problems) + hint)

    log("Checking the Banjo-Kazooie ROM.")
    try:
        vanilla = bkrom.load_vanilla(project.vanilla_rom)
    except (OSError, bkrom.RomError) as e:
        raise ConvertError(str(e))

    log("Loading the romhack.")
    try:
        romhack, patch = load_romhack(vanilla, project.romhack, log)
    except (OSError, bps.BpsError) as e:
        raise ConvertError(str(e))

    log("Finding the romhack's code.")
    try:
        analysis = codeblock.analyze(vanilla, VANILLA_SYMS, romhack)
    except (codeblock.CodeBlockError, bkrom.RomError) as e:
        raise ConvertError(str(e))
    block = analysis.block
    log(f"Code block: ROM {block.rom:#x} -> RAM {block.vram:#x}, {block.size:#x} bytes, "
        f"{len(analysis.functions)} functions"
        + (f" ({len(analysis.extra_functions)} written by the romhack's author)" if analysis.extra_functions else ""))
    for warning in analysis.warnings:
        log("Warning: " + warning)

    note_counts = project.note_counts
    if project.note_saving:
        if not note_counts:
            log("Counting notes.")
            try:
                note_counts = notecount.count_notes(romhack)
            except bkrom.RomError as e:
                raise ConvertError(f"Couldn't count the notes: {e}\nFill in the note table yourself, "
                                   "or turn note saving off.")
        check_note_counts(romhack, note_counts, log)
        total = sum(static + bundle for static, bundle in note_counts.values())
        log(f"Note saving: {total} notes in {len(note_counts)} maps.")
    else:
        log("Note saving is turned off for this romhack.")

    os.makedirs(project.output_dir, exist_ok=True)
    mod_id = project.mod.mod_id
    with tempfile.TemporaryDirectory(prefix="bkconv_") as tmp:
        def tmp_path(name):
            return os.path.join(tmp, name)

        with open(tmp_path("baserom.z64"), "wb") as file:
            file.write(vanilla)
        with open(tmp_path("romhack.z64"), "wb") as file:
            file.write(romhack)
        toml = codeblock.to_toml(analysis)
        with open(tmp_path("romhack_syms.toml"), "w") as file:
            file.write(toml)
        with open(os.path.join(project.output_dir, f"{mod_id}_syms.toml"), "w") as file:
            file.write(toml)

        log("Recompiling the romhack's code changes.")
        # BKRecompRomhackTool dumps a decompressed romhack.z64 into its working directory.
        os.makedirs(tmp_path("tool"))
        tool_output = _run_tool([project.romhack_tool, tmp_path("baserom.z64"), tmp_path("romhack.z64"), VANILLA_SYMS,
                                 tmp_path("romhack_syms.toml"), tmp_path("romhack_syms.bin"),
                                 tmp_path("romhack_binary.bin")], tmp_path("tool"), log)
        # The tool lists changed functions under each "  .section" line.
        report = tool_output.partition("Patched functions:")[2]
        patched = sum(1 for line in report.splitlines() if line.startswith("  ") and not line.startswith("  ."))
        log(f"The romhack changes {patched} of the game's own functions.")

        log("Adding the compatibility code.")
        with open(tmp_path("compat_binary.bin"), "wb") as file:
            file.write(compat_config.configured_binary(note_counts, not project.note_saving, project.hidden_actors))
        _run_tool([find_merger(), VANILLA_SYMS, compat_config.syms_path(), tmp_path("compat_binary.bin"),
                   tmp_path("romhack_syms.bin"), tmp_path("romhack_binary.bin"),
                   tmp_path("mod_syms.bin"), tmp_path("mod_binary.bin")], tmp, log)

        with open(tmp_path("mod_syms.bin"), "rb") as file:
            mod_syms = file.read()
        with open(tmp_path("mod_binary.bin"), "rb") as file:
            mod_binary = file.read()

    nrm_name = f"{mod_id}.nrm"
    nrm_path = os.path.join(project.output_dir, nrm_name)
    mod_files.write_nrm(nrm_path, project.mod, mod_syms, mod_binary, patch, project.thumbnail_path())
    written = [nrm_path]
    log(f"Wrote {nrm_path}")

    if project.make_thunderstore:
        zip_path = os.path.join(project.output_dir, f"{project.thunderstore.package_name}-{project.mod.version}.zip")
        mod_files.write_thunderstore(zip_path, project.mod, project.thunderstore, nrm_path, nrm_name)
        written.append(zip_path)
        log(f"Wrote {zip_path}")
    return written
