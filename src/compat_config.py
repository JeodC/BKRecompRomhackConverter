"""Fills in the prebuilt compatibility code's config block."""

import os
import struct

COMPAT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compat")
MAGIC = b"BKRCCFG1"
MAX_MAPS = 256
MAX_HIDDEN_ACTORS = 16
FLAG_DISABLE_NOTE_SAVING = 1


def configured_binary(note_counts, disable_note_saving=False, hidden_actors=()):
    """mod_binary.bin with the config block filled in"""
    with open(os.path.join(COMPAT_DIR, "mod_binary.bin"), "rb") as file:
        binary = bytearray(file.read())
    if binary.count(MAGIC) != 1:
        raise RuntimeError("The prebuilt compatibility binary is damaged (config block not found)")
    if len(note_counts) > MAX_MAPS:
        raise ValueError(f"At most {MAX_MAPS} maps can have notes")
    if len(hidden_actors) > MAX_HIDDEN_ACTORS:
        raise ValueError(f"At most {MAX_HIDDEN_ACTORS} hidden actors are supported")

    maps = sorted((map_id, static, bundle) for map_id, (static, bundle) in note_counts.items() if static or bundle)
    config = struct.pack(">8sIII", MAGIC, FLAG_DISABLE_NOTE_SAVING if disable_note_saving else 0,
                         len(maps), len(hidden_actors))
    config += b"".join(struct.pack(">HHHH", map_id, static, bundle, 0) for map_id, static, bundle in maps)
    config += bytes(8 * (MAX_MAPS - len(maps)))
    config += b"".join(struct.pack(">HHHH", actor, model, type_field, 0) for actor, model, type_field in hidden_actors)
    config += bytes(8 * (MAX_HIDDEN_ACTORS - len(hidden_actors)))

    offset = binary.find(MAGIC)
    binary[offset:offset + len(config)] = config
    return bytes(binary)


def syms_path():
    return os.path.join(COMPAT_DIR, "mod_syms.bin")
