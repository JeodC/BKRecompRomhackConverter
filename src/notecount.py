"""Counts the notes in each map, matching Banjo: Recompiled's note saving."""

import re
import struct

import bkrom, mips

CORE2_TEXT_SIZE = 0xDC600
CORE2_ASSETS_LUI = 0xB4C60
CORE2_ASSETS_ADDIU = 0xB4C6C
ASSET_TABLE_ROM = 0x5E90
MAP_MODEL_DESCRIPTIONS = 0x7650
SETUP_ASSET_BASE = 0x71C
LAST_MAP_ID = 0x99
SPRITE_ASSET_OFFSET = 0x572
ASSET_6D6_SPRITE_MUSIC_NOTE = 0x6D6
ACTOR_9_MM_HUT = 0x9
ACTOR_C_MUD_HUT = 0xC
ACTOR_51_MUSIC_NOTE = 0x51

HUT_BUNDLE_NOTES = 5
EMPTY_ASSET_FLAG = 4

NODE_PROP_SIZE = 20
OTHER_NODE_SIZE = 12
PROP_SIZE = 12


class SetupParseError(bkrom.RomError):
    pass


def _lui_addiu_value(code, lui_at, addiu_at):
    """The value a `lui` + `addiu` pair loads, or None if the words aren't that pair"""
    if max(lui_at, addiu_at) + 4 > len(code):
        return None
    (lui,), (addiu,) = struct.unpack_from(">I", code, lui_at), struct.unpack_from(">I", code, addiu_at)
    if (mips.opcode(lui) != mips.OP_LUI or mips.opcode(addiu) != mips.OP_ADDIU
            or mips.rs_field(addiu) != mips.rt_field(lui)):
        return None
    return ((lui & 0xFFFF) << 16) + mips.immediate(addiu)


# u32 count, u32 pad, then count entries of {u32 offset, s16 compFlag, s16 flag}. The data
# follows the entries (assetCache_init).
class AssetTable:
    def __init__(self, rom, start):
        self.rom = rom
        (self.count,) = struct.unpack_from(">I", rom, start)
        self.entries = [struct.unpack_from(">Ihh", rom, start + 8 + i * 8) for i in range(self.count)]
        self.data_start = start + 8 + self.count * 8

    def get(self, asset_id):
        """The asset's bytes, inflated when compressed, or None for an empty slot"""
        if asset_id + 1 >= self.count:
            return None
        offset, compressed, flag = self.entries[asset_id]
        size = self.entries[asset_id + 1][0] - offset  # asset_getCompressedSize
        if flag == EMPTY_ASSET_FLAG or size <= 0:
            return None
        begin = self.data_start + offset
        if compressed & 1:
            return bkrom.decompress(self.rom, begin, size)[0]
        return self.rom[begin:begin + size]


def _looks_like_table(rom, start):
    """Whether every entry has valid flags and every compressed setup has a stream header"""
    if start < 0 or start + 8 > len(rom):
        return False
    count, pad = struct.unpack_from(">II", rom, start)
    data_start = start + 8 + count * 8
    if not SETUP_ASSET_BASE + LAST_MAP_ID < count <= 0x10000 or pad != 0xFFFFFFFF or data_start >= len(rom):
        return False
    entries = list(struct.iter_unpack(">Ihh", rom[start + 8:data_start]))
    if any(compressed not in (0, 1) or not 0 <= flag <= EMPTY_ASSET_FLAG for _, compressed, flag in entries):
        return False
    setup_entries = entries[SETUP_ASSET_BASE + 1:SETUP_ASSET_BASE + LAST_MAP_ID + 1]
    setups = [entry for entry in setup_entries if entry[2] != EMPTY_ASSET_FLAG]
    headers = [rom[data_start + offset:data_start + offset + 2] == bkrom.RAREZIP_MAGIC
               for offset, compressed, _ in setups if compressed]
    return bool(headers) and all(headers)


# A table header: a count of 0x700..0x10000, then the 0xFFFFFFFF pad word.
_TABLE_HEADER = re.compile(rb"\x00(?:\x00[\x07-\xff].|\x01\x00\x00)\xff\xff\xff\xff", re.DOTALL)


def find_asset_table(rom, core2_text=None):
    """assets_ROM_START, read from assetCache_init's code when possible"""
    if core2_text is not None:
        start = _lui_addiu_value(core2_text, CORE2_ASSETS_LUI, CORE2_ASSETS_ADDIU)
        if start is not None and _looks_like_table(rom, start):
            return start
    if _looks_like_table(rom, ASSET_TABLE_ROM):
        return ASSET_TABLE_ROM
    for match in _TABLE_HEADER.finditer(rom):
        if _looks_like_table(rom, match.start()):
            return match.start()
    raise bkrom.RomError("Couldn't find the asset table")


def _scale_down(value):  # coords_scale (core2/coords.c), with C's truncating division
    return value // 1000 if value >= 0 else -(-value // 1000) - 1


def cube_bounds(table, core2_data, map_id):
    """(min, max) cube bounds of a map (mapModel_getCubeBounds), or None without a description"""
    offset = MAP_MODEL_DESCRIPTIONS
    while offset + 24 <= len(core2_data):
        entry = struct.unpack_from(">9h", core2_data, offset)  # map, opa, xlu, min[3], max[3]
        if entry[0] == 0:
            return None
        if entry[0] == map_id:
            model = table.get(entry[1] & 0xFFFF)
            if not model:
                return None
            vertex_list = struct.unpack_from(">i", model, 0x10)[0]  # BKModelBin.vtx_list_offset
            min_coord = struct.unpack_from(">3h", model, vertex_list)  # BKVertexList.minCoord
            max_coord = struct.unpack_from(">3h", model, vertex_list + 6)  # BKVertexList.maxCoord
            return (
                tuple(_scale_down(min_coord[i]) + entry[3 + i] for i in range(3)),
                tuple(_scale_down(max_coord[i]) + entry[6 + i] for i in range(3)),
            )
        offset += 24
    return None


class _File:
    """core2/file.c's asset reader (FILE_MODE_2_FROM_ASSET)"""

    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.held_marker = -1

    def read(self, size):
        if self.pos + size > len(self.data):
            raise SetupParseError(f"Setup read past its end at {self.pos:#x}")
        chunk = self.data[self.pos:self.pos + size]
        self.pos += size
        return chunk

    def expect(self, value):  # file_isNextByteExpected
        if self.held_marker == -1:
            byte = self.read(1)[0]
            if byte == value:
                return True
            # A mismatched marker is held for the next check, but plain reads skip past it.
            self.held_marker = byte
            return False
        if self.held_marker == value:
            self.held_marker = -1
            return True
        return False

    def read_if(self, value, size):  # file_get*_ifExpected
        return self.read(size) if self.expect(value) else None


def _read_until(reader, end_marker, body):
    """while (!file_isNextByteExpected(reader, end_marker)) body(), raising where the game would hang"""
    while not reader.expect(end_marker):
        before = (reader.pos, reader.held_marker)
        body()
        if (reader.pos, reader.held_marker) == before:
            raise SetupParseError(f"Setup parser stalls on byte {reader.held_marker:#04x} at {reader.pos:#x}")


def _count_note_sprites(props):
    count = 0
    for i in range(0, len(props), PROP_SIZE):
        word0, flags = struct.unpack_from(">I6xH", props, i)
        if flags & 3:  # bit 0 actor prop, bit 1 model prop
            continue
        if (word0 >> 20) + SPRITE_ASSET_OFFSET == ASSET_6D6_SPRITE_MUSIC_NOTE:
            count += 1
    return count


def _check_cube_count(reader, count, kind):
    if count > 63:  # Cube.prop1Cnt and prop2Cnt are 6 bits, so the game misreads the file past this
        raise SetupParseError(f"Cube with {count} {kind} at {reader.pos:#x}")


def _cube_from_file(reader):
    """(nodes, props) of one cube (code7AF80_initCubeFromFile)"""
    nodes = b""
    count = reader.read_if(0x0A, 1)
    if count is not None:
        _check_cube_count(reader, count[0], "nodes")
        nodes = reader.read_if(0x0B, count[0] * NODE_PROP_SIZE) or b""
    else:
        count = reader.read_if(0x06, 1)
        if count is not None:
            _check_cube_count(reader, count[0], "nodes")
            reader.read_if(0x07, count[0] * OTHER_NODE_SIZE)
    count = reader.read_if(0x08, 1)
    if count is None:
        return nodes, b""
    _check_cube_count(reader, count[0], "props")
    props = reader.read_if(0x09, count[0] * PROP_SIZE)
    if props is None and count[0]:
        raise SetupParseError(f"Prop list without its 0x09 marker at {reader.pos:#x}")
    return nodes, props or b""


def _load_cube_slot(reader, cube):
    """(notes, the cube afterwards) for one slot (Recompiled's __code7AF80_initCubeFromFile)"""

    def body():
        nonlocal cube
        if reader.read_if(0x00, 12) is not None:
            reader.read(12)
        elif reader.read_if(0x02, 12) is None and reader.expect(0x03):
            cube = _cube_from_file(reader)  # starts with cube_free(), so the slot's last 0x03 block wins

    _read_until(reader, 0x01, body)
    return _count_note_sprites(cube[1]), cube


def _cube_list_from_file(reader, bounds, nodes):
    """Notes in a cube section (cubeList_fromFile), adding its node lists to `nodes`"""
    low = reader.read_if(0x01, 12)
    if low is None:
        raise SetupParseError("Cube section without bounds")
    low = struct.unpack(">3i", low)
    high = struct.unpack(">3i", reader.read(12))
    notes = 0
    # Slots outside the map model's bounds all load into one fallback cube
    # (__code7AF80_getCubeAtPosition), so an empty one there re-counts the last one's notes.
    fallback = (b"", b"")
    for x in range(low[0], high[0] + 1):
        for y in range(low[1], high[1] + 1):
            for z in range(low[2], high[2] + 1):
                inside = bounds is None or all(bounds[0][axis] <= coord <= bounds[1][axis]
                                               for axis, coord in enumerate((x, y, z)))
                slot_notes, cube = _load_cube_slot(reader, (b"", b"") if inside else fallback)
                if inside:
                    nodes.append(cube[0])
                else:
                    fallback = cube
                notes += slot_notes
    nodes.append(fallback[0])
    reader.expect(0x00)
    return notes


def _camera_node(reader):
    """__ncCameraNodeList_nodeFromFile and cameraNodeType*_fromFile"""
    node_type = reader.read_if(0x02, 1)
    if node_type is None:
        raise SetupParseError(f"Camera node without a type at {reader.pos:#x}")
    node_type = node_type[0]

    def pivot_or_zoom():
        if reader.read_if(0x01, 12) is not None:
            return
        if reader.read_if(0x02, 8) is not None or reader.read_if(0x03, 8) is not None:
            return
        if node_type == 3 and reader.read_if(0x06, 8) is not None:
            return
        if reader.read_if(0x04, 12) is None:
            reader.read_if(0x05, 4)

    def static():
        if reader.read_if(0x01, 12) is None:
            reader.read_if(0x02, 12)

    def random():
        reader.read_if(0x01, 4)

    body = {1: pivot_or_zoom, 2: static, 3: pivot_or_zoom, 4: random}.get(node_type)
    if body is not None:
        _read_until(reader, 0x00, body)


def _cameras_from_file(reader):
    """ncCameraNodeList_fromFile (core2/nc/cameranodelist.c)"""

    def body():
        if reader.read_if(0x01, 2) is not None:
            _camera_node(reader)

    _read_until(reader, 0x00, body)


def _lights_from_file(reader):
    """lightingVectorList_fromFile (core2/code_AC520.c)"""

    def body():
        _ = reader.expect(0x01) and reader.read_if(0x02, 12) and reader.read_if(0x03, 8) and reader.read_if(0x04, 12)

    _read_until(reader, 0x00, body)


def load_setup(setup, bounds=None):
    """(static notes, node lists) of a decompressed setup file (func_80335140)"""
    reader = _File(setup)
    notes = 0
    nodes = []

    def body():
        nonlocal notes
        if reader.expect(0x02):
            pass
        elif reader.expect(0x01):
            notes += _cube_list_from_file(reader, bounds, nodes)
        elif reader.expect(0x03):
            _cameras_from_file(reader)
        elif reader.expect(0x04):
            _lights_from_file(reader)

    _read_until(reader, 0x00, body)
    return notes, nodes


def bundle_notes_from_nodes(nodes):
    """Notes the setup's actors drop, from the vanilla sources only"""
    mm_huts = mud_hut_notes = note_actors = 0
    for node_list in nodes:
        for i in range(0, len(node_list), NODE_PROP_SIZE):
            _, y, _, flags, actor = struct.unpack_from(">3hHH", node_list, i)
            if flags & 1 or (flags >> 1) & 0x3F != 6:  # waypoint, or not an actor node
                continue
            if actor == ACTOR_9_MM_HUT:
                mm_huts += 1
            elif actor == ACTOR_C_MUD_HUT and int((y - 600.0) / 430.0) == 2:  # hut_id 2 (BGS/ch/mudhut.c)
                mud_hut_notes += HUT_BUNDLE_NOTES
            elif actor == ACTOR_51_MUSIC_NOTE:
                note_actors += 1
    # Only the first MM hut smashed drops its bundle (MM/ch/hut.c).
    return (HUT_BUNDLE_NOTES if mm_huts else 0) + mud_hut_notes + note_actors


def _find_core2(segments):
    """core2's (text, data), or (None, None) when the romhack rebuilt it"""
    return next(((text, data) for _, text, data in segments if len(text) == CORE2_TEXT_SIZE), (None, None))


def count_notes(rom):
    """Map id -> (static notes, estimated bundle notes) for every map with either"""
    core2_text, core2_data = _find_core2(bkrom.find_segments(rom))
    table = AssetTable(rom, find_asset_table(rom, core2_text))
    counts = {}
    for map_id in range(1, LAST_MAP_ID + 1):
        setup = table.get(map_id + SETUP_ASSET_BASE)
        if not setup:
            continue
        static, nodes = load_setup(setup)
        if static and core2_data:  # with no notes in any slot there is nothing to re-count
            try:
                bounds = cube_bounds(table, core2_data, map_id)
            except (bkrom.RomError, struct.error):
                bounds = None
            static, nodes = load_setup(setup, bounds)
        bundle = bundle_notes_from_nodes(nodes)
        if static or bundle:
            counts[map_id] = (static, bundle)
    return counts


# The map info list, D_8036B810 (core2/gc/section.c), starts with a {0, 0, name} marker entry followed by
# {MAP_1_SM_SPIRAL_MOUNTAIN, LEVEL_B_SPIRAL_MOUNTAIN, name}.
_MAP_INFO_START = re.compile(rb"\x00\x00\x00\x00\x80...\x00\x01\x00\x0B\x80...", re.DOTALL)


def map_levels(rom):
    """Map id -> level id from the game's map info list, or {} if it can't be found"""
    for _, _, data in bkrom.find_segments(rom):
        match = _MAP_INFO_START.search(data)
        if not match or match.start() % 4:
            continue
        levels = {}
        for offset in range(match.start() + 8, len(data) - 7, 8):  # {s16 map, s16 level, char *name}
            map_id, level_id = struct.unpack_from(">hh", data, offset)
            if map_id == 0:
                return levels
            levels[map_id] = level_id
    return {}
