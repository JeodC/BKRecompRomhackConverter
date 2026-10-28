"""BPS patch apply and create."""

import zlib

MAGIC = b"BPS1"

SOURCE_READ, TARGET_READ, SOURCE_COPY, TARGET_COPY = range(4)


class BpsError(Exception):
    pass


def _read_varint(data, pos):
    value, shift = 0, 1
    while True:
        if pos >= len(data):
            raise BpsError("Patch is truncated")
        byte = data[pos]
        pos += 1
        value += (byte & 0x7F) * shift
        if byte & 0x80:
            return value, pos
        shift <<= 7
        value += shift


def _write_varint(out, value):
    while True:
        byte = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(0x80 | byte)
            return
        out.append(byte)
        value -= 1


def _read_header(patch):
    """(source size, target size, where the actions start)"""
    if len(patch) < 4 + 12 or patch[:4] != MAGIC:
        raise BpsError("Not a BPS patch")
    pos = 4
    source_size, pos = _read_varint(patch, pos)
    target_size, pos = _read_varint(patch, pos)
    metadata_size, pos = _read_varint(patch, pos)
    return source_size, target_size, pos + metadata_size


def source_crc(patch):
    """CRC32 of the ROM the patch applies to, once the patch checks out as intact"""
    _read_header(patch)
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise BpsError("The patch file is damaged (its checksum doesn't match).")
    return int.from_bytes(patch[-12:-8], "little")


def apply(source, patch):
    source_size, target_size, pos = _read_header(patch)
    wanted = source_crc(patch)
    if len(source) != source_size or zlib.crc32(source) != wanted:
        raise BpsError("This patch was made for a different ROM.")

    target = bytearray(target_size)
    output_pos = 0
    source_cursor = 0
    target_cursor = 0
    actions_end = len(patch) - 12
    while pos < actions_end:
        action, pos = _read_varint(patch, pos)
        command = action & 3
        length = (action >> 2) + 1
        if output_pos + length > target_size:
            raise BpsError("Patch writes past the end of the target")

        if command == SOURCE_READ:
            target[output_pos:output_pos + length] = source[output_pos:output_pos + length]
        elif command == TARGET_READ:
            target[output_pos:output_pos + length] = patch[pos:pos + length]
            pos += length
        else:
            delta, pos = _read_varint(patch, pos)
            delta = -(delta >> 1) if delta & 1 else delta >> 1
            if command == SOURCE_COPY:
                source_cursor += delta
                target[output_pos:output_pos + length] = source[source_cursor:source_cursor + length]
                source_cursor += length
            else:
                target_cursor += delta
                gap = output_pos - target_cursor
                if gap <= 0:
                    raise BpsError("Invalid target copy")
                # An overlapping copy repeats the last `gap` bytes of output.
                pattern = bytes(target[target_cursor:target_cursor + min(gap, length)])
                target[output_pos:output_pos + length] = (pattern * (length // len(pattern) + 1))[:length]
                target_cursor += length
        output_pos += length

    if output_pos != target_size:
        raise BpsError("Patch did not produce a complete ROM")
    if zlib.crc32(target) != int.from_bytes(patch[-8:-4], "little"):
        raise BpsError("Patched ROM failed its checksum")
    return bytes(target)


_BLOCK_SIZE = 64


def create(source, target):
    """A patch from `source` to `target`, in 64-byte blocks"""
    patch = bytearray(MAGIC)
    _write_varint(patch, len(source))
    _write_varint(patch, len(target))
    _write_varint(patch, 0)

    target_cursor = 0

    def emit(command, start, end):
        nonlocal target_cursor
        _write_varint(patch, ((end - start - 1) << 2) | command)
        if command == TARGET_READ:
            patch.extend(target[start:end])
        elif command == TARGET_COPY:
            delta = (start - 1) - target_cursor
            _write_varint(patch, ((-delta) << 1) | 1 if delta < 0 else delta << 1)
            target_cursor = start - 1 + (end - start)

    shared_size = min(len(source), len(target))
    run_command = None
    run_start = 0
    for pos in range(0, len(target), _BLOCK_SIZE):
        block = target[pos:pos + _BLOCK_SIZE]
        if pos + len(block) <= shared_size and source[pos:pos + len(block)] == block:
            command = SOURCE_READ
        elif pos and block.count(target[pos - 1]) == len(block):
            command = TARGET_COPY
        else:
            command = TARGET_READ
        if command != run_command:
            if run_command is not None:
                emit(run_command, run_start, pos)
            run_command, run_start = command, pos
    if run_command is not None:
        emit(run_command, run_start, len(target))

    patch += zlib.crc32(source).to_bytes(4, "little")
    patch += zlib.crc32(target).to_bytes(4, "little")
    patch += zlib.crc32(patch).to_bytes(4, "little")
    return bytes(patch)
