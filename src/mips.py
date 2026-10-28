"""Enough MIPS decoding to follow control flow and compare relocated code."""

import struct

OP_SPECIAL = 0x00
OP_REGIMM = 0x01
OP_J = 0x02
OP_JAL = 0x03
OP_BEQ = 0x04
OP_ADDIU = 0x09
OP_ORI = 0x0D
OP_LUI = 0x0F
OP_COP1 = 0x11

BRANCH_OPCODES = {0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17}
REGIMM_BRANCHES = {0x00, 0x01, 0x02, 0x03, 0x10, 0x11, 0x12, 0x13}
COP1_BRANCH = 0x08

ZERO, A0, A1, A2 = 0, 4, 5, 6
JR_RA = 0x03E00008


def opcode(word):
    return word >> 26


def rs_field(word):
    return (word >> 21) & 0x1F


def rt_field(word):
    return (word >> 16) & 0x1F


def immediate(word):
    """The low 16 bits, sign-extended"""
    value = word & 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def addend(word):
    """What an addiu (sign-extended) or ori (not) adds to its source register"""
    return immediate(word) if opcode(word) == OP_ADDIU else word & 0xFFFF


def jump_target(word, address):
    return ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def branch_target(word, address):
    """Where a branch goes, or None if the word isn't one"""
    op = opcode(word)
    if (op in BRANCH_OPCODES or (op == OP_REGIMM and rt_field(word) in REGIMM_BRANCHES)
            or (op == OP_COP1 and rs_field(word) == COP1_BRANCH)):
        return address + 4 + (immediate(word) << 2)
    return None


def is_unconditional_branch(word):
    return opcode(word) == OP_BEQ and rs_field(word) == ZERO and rt_field(word) == ZERO


def is_prologue(word):
    """addiu $sp, $sp, -N"""
    return (word >> 16) == 0x27BD and (word & 0x8000)


def relocation_mask(word):
    """The instruction without the fields a relocation can change"""
    op = opcode(word)
    if op in (OP_J, OP_JAL):
        return word & 0xFC000000
    if op == OP_SPECIAL or branch_target(word, 0) is not None:
        return word
    return word & 0xFFFF0000


def read_words(data, start=0, end=None):
    end = len(data) if end is None else end
    count = max(0, (end - start) // 4)
    return list(struct.unpack_from(f">{count}I", data, start))


def function_size(code, code_vram, start, limit):
    """Size of the function at `start`, stopping at `limit`"""
    address = start
    furthest_branch = start
    while address < limit:
        word = int.from_bytes(code[address - code_vram:address - code_vram + 4], "big")
        target = branch_target(word, address)
        if target is not None and target > furthest_branch:
            furthest_branch = target
        leaves = (word == JR_RA or is_unconditional_branch(word)
                  or (opcode(word) == OP_J and not start <= jump_target(word, address) < limit))
        # A return is only the end once no branch still lands past it.
        if leaves and address >= furthest_branch:
            return min(address + 8, limit) - start  # with the delay slot
        address += 4
    return limit - start
