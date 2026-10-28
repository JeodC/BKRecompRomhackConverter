"""Checks the modder's details and writes the .nrm and Thunderstore zip."""

import json
import re
import zipfile
from dataclasses import dataclass, field

THUNDERSTORE_DESCRIPTION_MAX = 250
ICON_SIZE = (256, 256)


@dataclass
class ModInfo:
    mod_id: str = ""
    version: str = "1.0.0"
    display_name: str = ""
    short_description: str = ""
    description: str = ""
    authors: list = field(default_factory=list)
    minimum_recomp_version: str = "1.0.0"


@dataclass
class ThunderstoreInfo:
    package_name: str = ""
    description: str = ""
    website_url: str = ""
    dependencies: list = field(default_factory=list)
    readme: str = ""
    changelog: str = ""
    icon_path: str = ""


def png_size(path):
    with open(path, "rb") as file:
        head = file.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def check_mod(mod, thumbnail_path):
    problems = []
    if not mod.mod_id:
        problems.append("Mod ID is empty.")
    elif not re.fullmatch(r"[a-z0-9_]+", mod.mod_id):
        problems.append("Mod ID must be lowercase letters, numbers and underscores, e.g. bk_jiggies_of_time.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", mod.version or ""):
        problems.append("Version must look like 1.0.1.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", mod.minimum_recomp_version or ""):
        problems.append("Minimum version must look like 1.0.0.")
    for label, value in (("Display name", mod.display_name), ("Short description", mod.short_description),
                         ("Description", mod.description)):
        if not value.strip():
            problems.append(f"{label} is empty.")
    if not [author for author in mod.authors if author.strip()]:
        problems.append("Authors is empty.")
    if thumbnail_path and png_size(thumbnail_path) is None:
        problems.append("In-game thumbnail must be a PNG file.")
    return problems


def check_thunderstore(thunderstore):
    problems = []
    if not thunderstore.package_name:
        problems.append("Package name is empty.")
    elif not re.fullmatch(r"[A-Za-z0-9_]+", thunderstore.package_name):
        problems.append("Package name may only use letters, numbers and underscores.")
    if not thunderstore.description.strip():
        problems.append("Description is empty.")
    elif len(thunderstore.description) > THUNDERSTORE_DESCRIPTION_MAX:
        problems.append(f"Description is {len(thunderstore.description)} characters, over the "
                        f"{THUNDERSTORE_DESCRIPTION_MAX} limit.")
    for dependency in thunderstore.dependencies:
        if not re.fullmatch(r"[A-Za-z0-9_]+-[A-Za-z0-9_]+-\d+\.\d+\.\d+", dependency):
            problems.append(f"Dependency '{dependency}' should look like Author-Package-1.0.0.")
    if not thunderstore.readme.strip():
        problems.append("README is empty.")
    if not thunderstore.icon_path:
        problems.append("Choose an icon.")
    else:
        size = png_size(thunderstore.icon_path)
        if size is None:
            problems.append("Icon must be a PNG file.")
        elif size != ICON_SIZE:
            problems.append(f"Icon must be exactly 256x256 pixels (yours is {size[0]}x{size[1]}).")
    return problems


def mod_json(mod):
    return {
        "authors": [author.strip() for author in mod.authors if author.strip()],
        "custom_gamemode": True,
        "description": mod.description,
        "display_name": mod.display_name,
        "game_id": "bk",
        "id": mod.mod_id,
        "minimum_recomp_version": mod.minimum_recomp_version,
        "short_description": mod.short_description,
        "version": mod.version,
    }


def write_nrm(path, mod, mod_syms, mod_binary, patch, thumbnail_path=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("mod.json", json.dumps(mod_json(mod), indent=4))
        archive.writestr("mod_syms.bin", mod_syms)
        archive.writestr("mod_binary.bin", mod_binary)
        archive.writestr("patch.bps", patch)
        if thumbnail_path:
            # The runtime reads thumb.png when there's no thumb.dds.
            archive.write(thumbnail_path, "thumb.png")


def write_thunderstore(path, mod, thunderstore, nrm_path, nrm_name):
    manifest = {
        "name": thunderstore.package_name,
        "version_number": mod.version,
        "website_url": thunderstore.website_url,
        "description": thunderstore.description,
        "dependencies": list(thunderstore.dependencies),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=4))
        archive.writestr("README.md", thunderstore.readme)
        archive.write(thunderstore.icon_path, "icon.png")
        if thunderstore.changelog.strip():
            archive.writestr("CHANGELOG.md", thunderstore.changelog)
        archive.write(nrm_path, nrm_name, compress_type=zipfile.ZIP_STORED)  # already compressed
