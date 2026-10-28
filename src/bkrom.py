"""Banjo-Kazooie ROM byte order, validation and compressed code segments."""

import hashlib
import zlib

import mips

VANILLA_SHA1 = "1fe1632098865f639e22c11b9a81ee8f29c75d7a"

VANILLA_SEGMENTS = {
    "core1": 0xF19250,
    "core2": 0xF37F90,
    "CC": 0xFA3FD0,
    "MMM": 0xFA5F50,
    "GV": 0xFA9150,
    "TTC": 0xFAE860,
    "MM": 0xFB24A0,
    "BGS": 0xFB44E0,
    "RBB": 0xFB9A30,
    "FP": 0xFBEBE0,
    "SM": 0xFC4810,
    "cutscenes": 0xFC6F20,
    "lair": 0xFC9150,
    "fight": 0xFD0420,
    "CCW": 0xFD6190,
}
LEVEL_OVERLAYS = [name for name in VANILLA_SEGMENTS if not name.startswith("core")]

BOOT_START, BOOT_END = 0x1050, 0x5BE0
RAREZIP_MAGIC = b"\x11\x72"


class RomError(Exception):
    pass


def swap16(data):
    swapped = bytearray(data)
    swapped[0::2], swapped[1::2] = data[1::2], data[0::2]
    return bytes(swapped)


def swap32(data):
    swapped = bytearray(len(data))
    for i in range(4):
        swapped[i::4] = data[3 - i::4]
    return bytes(swapped)


def to_z64(data):
    magic = data[:4]
    if magic == b"\x80\x37\x12\x40":
        return bytes(data)
    if magic == b"\x37\x80\x40\x12":  # .v64
        return swap16(data)
    if magic == b"\x40\x12\x37\x80":  # .n64
        return swap32(data)
    raise RomError("Not an N64 ROM")


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def load_vanilla(path):
    with open(path, "rb") as file:
        rom = to_z64(file.read())
    if sha1(rom) != VANILLA_SHA1:
        raise RomError("This isn't the Banjo-Kazooie NTSC-U 1.0 (Rev 0) ROM that Banjo: Recompiled uses.")
    return rom


def decompress(rom, offset, max_compressed=0x200000):
    """(data, offset just past the stream) for the compressed stream at `offset`"""
    if rom[offset:offset + 2] != RAREZIP_MAGIC:
        raise RomError(f"No compressed data at {offset:#x}")
    stream = rom[offset + 6:offset + 6 + max_compressed]
    inflater = zlib.decompressobj(-15)
    try:
        data = inflater.decompress(stream)
    except zlib.error as e:
        raise RomError(f"Compressed data at {offset:#x} is damaged: {e}") from None
    if not inflater.eof:
        raise RomError(f"Compressed data at {offset:#x} is truncated")
    # Not checked against the size in the header: Backpack writes setup sizes unpadded,
    # and the game inflates the whole stream anyway (assetcache_get).
    return data, offset + 6 + len(stream) - len(inflater.unused_data)


def read_segment(rom, offset):
    """(text, data) of a code segment: two compressed streams back to back"""
    text, end = decompress(rom, offset)
    data, _ = decompress(rom, end)
    return text, data


def find_segments(rom):
    """(rom offset, text, data) for every code segment the boot code points at"""
    segment_starts = set()
    upper_halves = {}
    for word in mips.read_words(rom, BOOT_START, BOOT_END):
        op = mips.opcode(word)
        if op == mips.OP_LUI:
            upper_halves[mips.rt_field(word)] = (word & 0xFFFF) << 16
        elif op in (mips.OP_ADDIU, mips.OP_ORI) and mips.rs_field(word) in upper_halves:
            address = upper_halves[mips.rs_field(word)] + mips.addend(word)
            if 0x1000 <= address < len(rom) - 6 and rom[address:address + 2] == RAREZIP_MAGIC:
                segment_starts.add(address)
    segments = []
    for start in sorted(segment_starts):
        try:
            segments.append((start,) + read_segment(rom, start))
        except RomError:
            continue
    return segments
