"""Command line, or the window when run without a command."""

import argparse
import sys

import bkrom, bps, codeblock, convert, notecount, project_file
from map_names import MAP_NAMES

COMMANDS = ("convert", "count-notes", "syms")


def _load_romhack(vanilla_path, romhack_path):
    vanilla = bkrom.load_vanilla(vanilla_path)
    romhack, _ = convert.load_romhack(vanilla, romhack_path, lambda message: print(message, file=sys.stderr))
    return vanilla, romhack


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # A project dropped onto the executable arrives as its only argument.
    if len(argv) == 1 and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        import gui
        gui.main(argv[0])
        return

    parser = argparse.ArgumentParser(prog="BKRecompRomhackConverter", description="BK Recomp Romhack Converter. "
                                     "Opens the window when run without a command, or with a project file.")
    commands = parser.add_subparsers(dest="command")

    command = commands.add_parser("convert", help="build the .nrm and Thunderstore zip from a saved project")
    command.add_argument("project", help="a .bkconv.json project saved from the window")

    command = commands.add_parser("count-notes", help="print the notes in each map")
    command.add_argument("romhack", help=".bps patch or patched ROM")
    command.add_argument("--vanilla", required=True, help="Banjo-Kazooie NTSC-U 1.0 (Rev 0) ROM")

    command = commands.add_parser("syms", help="write the symbol file BKRecompRomhackTool takes")
    command.add_argument("romhack", help=".bps patch or patched ROM")
    command.add_argument("--vanilla", required=True, help="Banjo-Kazooie NTSC-U 1.0 (Rev 0) ROM")
    command.add_argument("-o", "--output", help="output .toml (default: print it)")

    args = parser.parse_args(argv)
    try:
        if args.command is None:
            import gui
            gui.main()
        elif args.command == "convert":
            convert.run(project_file.load(args.project))
        elif args.command == "count-notes":
            _, romhack = _load_romhack(args.vanilla, args.romhack)
            counts = notecount.count_notes(romhack)
            print("map   static   bundle*  vanilla name")
            for map_id, (static, bundle) in sorted(counts.items()):
                print(f"0x{map_id:02X}  {static:6}  {bundle or '':>8}  {MAP_NAMES.get(map_id, '')}")
            total_static = sum(static for static, _ in counts.values())
            total_bundle = sum(bundle for _, bundle in counts.values())
            print(f"total {total_static:6}  {total_bundle:8}")
            print("* estimated from note-dropping huts and placed note actors")
        elif args.command == "syms":
            vanilla, romhack = _load_romhack(args.vanilla, args.romhack)
            toml = codeblock.to_toml(codeblock.analyze(vanilla, convert.VANILLA_SYMS, romhack))
            if args.output:
                with open(args.output, "w") as file:
                    file.write(toml)
            else:
                sys.stdout.write(toml)
    except (convert.ConvertError, bkrom.RomError, bps.BpsError, codeblock.CodeBlockError,
            project_file.ProjectFileError, OSError) as error:
        sys.exit(f"Error: {error}")


if __name__ == "__main__":
    main()
