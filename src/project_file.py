"""Conversion settings, saved as a .bkconv.json file next to the modder's files."""

import json
import os
from dataclasses import asdict, dataclass, field

from mod_files import ModInfo, ThunderstoreInfo

PROJECT_SUFFIX = ".bkconv.json"
_PATH_FIELDS = ("vanilla_rom", "romhack", "romhack_tool", "output_dir", "thumbnail")
_THUNDERSTORE_PATH_FIELDS = ("icon_path",)


class ProjectFileError(Exception):
    pass


@dataclass
class Project:
    vanilla_rom: str = ""
    romhack: str = ""
    romhack_tool: str = ""
    output_dir: str = ""
    thumbnail: str = ""
    mod: ModInfo = field(default_factory=ModInfo)
    thunderstore: ThunderstoreInfo = field(default_factory=ThunderstoreInfo)
    make_thunderstore: bool = True
    note_saving: bool = True
    note_counts: dict = field(default_factory=dict)
    hidden_actors: list = field(default_factory=list)

    def thumbnail_path(self):
        return self.thumbnail or self.thunderstore.icon_path


def _relative(path, base):
    if not path:
        return path
    try:
        return os.path.relpath(path, base)
    except ValueError:  # different drive
        return path


def _absolute(path, base):
    return os.path.normpath(os.path.join(base, path)) if path else path


def save(project, path):
    base = os.path.dirname(os.path.abspath(path))
    data = asdict(project)
    for key in _PATH_FIELDS:
        data[key] = _relative(data[key], base)
    for key in _THUNDERSTORE_PATH_FIELDS:
        data["thunderstore"][key] = _relative(data["thunderstore"][key], base)
    data["note_counts"] = {f"0x{int(map_id):02X}": counts for map_id, counts in sorted(project.note_counts.items())}
    data["hidden_actors"] = [[f"0x{value:04X}" for value in row] for row in project.hidden_actors]
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load(path):
    with open(path, encoding="utf-8") as file:
        text = file.read()
    try:
        return _parse(json.loads(text), os.path.dirname(os.path.abspath(path)))
    except (ValueError, TypeError, AttributeError) as error:
        raise ProjectFileError(f"{os.path.basename(path)} isn't a valid project file ({error}).") from None


def _parse(data, base):
    project = Project(**{key: value for key, value in data.items() if key not in ("mod", "thunderstore")})
    project.mod = ModInfo(**data.get("mod", {}))
    project.thunderstore = ThunderstoreInfo(**data.get("thunderstore", {}))
    for key in _PATH_FIELDS:
        setattr(project, key, _absolute(getattr(project, key), base))
    for key in _THUNDERSTORE_PATH_FIELDS:
        setattr(project.thunderstore, key, _absolute(getattr(project.thunderstore, key), base))
    project.note_counts = {int(map_id, 0): list(counts) for map_id, counts in project.note_counts.items()}
    project.hidden_actors = [[int(value, 0) if isinstance(value, str) else value for value in row]
                             for row in project.hidden_actors]
    return project
