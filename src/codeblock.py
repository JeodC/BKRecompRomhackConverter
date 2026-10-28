"""Builds BKRecompRomhackTool's symbol file for a Banjo's Backpack code block."""

import bisect
import tomllib
from dataclasses import dataclass, field

import bkrom, mips

OVERLAY_VRAM = 0x803863F0
_MATCH_WORDS = 32
_SEARCH_WORDS = 0x4000


class CodeBlockError(Exception):
    pass


@dataclass
class CodeBlock:
    rom: int
    vram: int
    size: int


@dataclass
class Analysis:
    block: CodeBlock
    functions: dict = field(default_factory=dict)
    extra_functions: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def load_vanilla_syms(path):
    with open(path, "rb") as file:
        sections = tomllib.load(file)["section"]
    return {section["name"].lstrip("."): section for section in sections}


def find_code_blocks(rom, segments):
    """Every raw ROM region a call copies into expansion RAM"""
    found = set()
    for _, text, _ in segments:
        words = mips.read_words(text)
        # Only calls near a `lui $a0` into expansion RAM can be one.
        calls = {call for at, word in enumerate(words)
                 if mips.opcode(word) == mips.OP_LUI and mips.rt_field(word) == mips.A0
                 and 0x8040 <= word & 0xFFFF < 0x8080
                 for call in range(max(0, at - 1), min(len(words) - 1, at + 17))
                 if mips.opcode(words[call]) == mips.OP_JAL}
        for call in sorted(calls):
            # The call's arguments, its delay slot included.
            registers = {mips.ZERO: 0}
            for word in words[max(0, call - 16):call] + [words[call + 1]]:
                op = mips.opcode(word)
                if op == mips.OP_LUI:
                    registers[mips.rt_field(word)] = (word & 0xFFFF) << 16
                elif op in (mips.OP_ADDIU, mips.OP_ORI) and mips.rs_field(word) in registers:
                    registers[mips.rt_field(word)] = (registers[mips.rs_field(word)] + mips.addend(word)) & 0xFFFFFFFF
            dest, source, size = registers.get(mips.A0), registers.get(mips.A1), registers.get(mips.A2)
            if None in (dest, source, size):
                continue
            # Added code lives past the vanilla 16 MB of ROM and goes to expansion RAM.
            if (0x80400000 <= dest < 0x80800000 and 0x1000000 <= source and 0 < size <= 0x400000
                    and source + size <= len(rom) and not (source | dest) & 0xF
                    and rom[source:source + 2] != bkrom.RAREZIP_MAGIC):
                found.add((source, dest, size))
    return [CodeBlock(*block) for block in sorted(found)]


def _without_relocations(words):
    return [mips.relocation_mask(word) for word in words]


def analyze(vanilla_rom, vanilla_syms_path, romhack_rom):
    segments = bkrom.find_segments(romhack_rom)
    if len(segments) < 3:
        raise CodeBlockError("Couldn't find the game's code in this ROM. Is it a Banjo-Kazooie romhack?")

    blocks = find_code_blocks(romhack_rom, segments)
    if not blocks:
        raise CodeBlockError("This romhack doesn't load a Banjo's Backpack code block the converter can read. "
                             "Romhacks with a compressed code block aren't supported yet.")
    if len(blocks) > 1:
        raise CodeBlockError("This romhack loads more than one code block, which isn't supported yet: "
                             + ", ".join(f"ROM {block.rom:#x} -> {block.vram:#x}" for block in blocks))
    block = blocks[0]
    analysis = Analysis(block)

    code = romhack_rom[block.rom:block.rom + block.size]
    masked_code = _without_relocations(mips.read_words(code))
    vanilla_syms = load_vanilla_syms(vanilla_syms_path)

    # Backpack keeps the overlays in ROM order, each followed by its data and BSS.
    cursor = 0
    for name in bkrom.LEVEL_OVERLAYS:
        text, data = bkrom.read_segment(vanilla_rom, bkrom.VANILLA_SEGMENTS[name])
        pattern = _without_relocations(mips.read_words(text, 0, _MATCH_WORDS * 4))
        search_end = min(cursor + _SEARCH_WORDS, len(masked_code) - len(pattern))
        overlay_at = next((at for at in range(cursor, search_end)
                           if masked_code[at:at + len(pattern)] == pattern), None)
        if overlay_at is None:
            raise CodeBlockError(f"Couldn't find the {name} overlay inside the code block.")
        for function in vanilla_syms[name]["functions"]:
            analysis.functions[block.vram + overlay_at * 4 + function["vram"] - OVERLAY_VRAM] = function["size"]
        cursor = overlay_at + (len(text) + len(data)) // 4

    _find_extra_functions(analysis, code, segments)
    _absorb_padding(analysis, code)
    return analysis


def _find_extra_functions(analysis, code, segments):
    """Adds the functions the romhack's author put in the block's spare space"""
    block_start = analysis.block.vram
    block_end = block_start + analysis.block.size
    function_starts = sorted(analysis.functions)

    def function_containing(address):
        i = bisect.bisect_right(function_starts, address) - 1
        if i >= 0 and address < function_starts[i] + analysis.functions[function_starts[i]]:
            return function_starts[i]
        return None

    def word_at(address):
        offset = address - block_start
        return int.from_bytes(code[offset:offset + 4], "big")

    def call_targets(words, address):
        for i, word in enumerate(words):
            if mips.opcode(word) == mips.OP_JAL:
                target = mips.jump_target(word, address + i * 4)
                if block_start <= target < block_end:
                    yield target

    candidates = set()
    for _, text, _ in segments:
        candidates.update(call_targets(mips.read_words(text), 0x80000000))
    for start, size in list(analysis.functions.items()):
        offset = start - block_start
        candidates.update(call_targets(mips.read_words(code, offset, offset + size), start))

    # Actor tables point at update functions from the block's data and the romhack's data segments.
    data_words = [word for _, _, data in segments for word in mips.read_words(data)]
    offset = 0
    for start in function_starts:
        data_words += mips.read_words(code, offset, start - block_start)
        offset = start - block_start + analysis.functions[start]
    data_words += mips.read_words(code, offset)
    for pointer in data_words:
        if (block_start <= pointer < block_end and not pointer & 3 and function_containing(pointer) is None
                and mips.is_prologue(word_at(pointer))):
            candidates.add(pointer)

    while candidates:
        start = candidates.pop()
        containing = function_containing(start)
        if containing == start:
            continue
        if containing is not None:
            analysis.warnings.append(f"Code jumps into the middle of func_{containing:08X} at {start:#x}")
            continue
        i = bisect.bisect_right(function_starts, start)
        next_start = function_starts[i] if i < len(function_starts) else block_end
        size = mips.function_size(code, block_start, start, next_start)
        analysis.functions[start] = size
        analysis.extra_functions.append(start)
        function_starts.insert(i, start)
        offset = start - block_start
        candidates.update(call_targets(mips.read_words(code, offset, offset + size), start))


def _absorb_padding(analysis, code):
    """Extends each function over the alignment nops before the next one"""
    block_start = analysis.block.vram
    function_starts = sorted(analysis.functions)
    for start, next_start in zip(function_starts, function_starts[1:]):
        end = start + analysis.functions[start]
        # Functions align to 16 bytes, so a longer run of zeros is free space.
        if 0 < next_start - end <= 0xC and not any(code[end - block_start:next_start - block_start]):
            analysis.functions[start] = next_start - start


def to_toml(analysis):
    block = analysis.block
    lines = [
        "# Generated by BK Recomp Romhack Converter",
        "[[section]]",
        'name = "codeseg"',
        f"rom = 0x{block.rom:X}",
        f"vram = 0x{block.vram:X}",
        f"size = 0x{block.size:X}",
        "",
        "functions = [",
    ]
    for start in sorted(analysis.functions):
        size = analysis.functions[start]
        lines.append(f'    {{ name = "func_{start:08X}", vram = 0x{start:08X}, size = 0x{size:08X} }},')
    lines.append("]")
    return "\n".join(lines) + "\n"
