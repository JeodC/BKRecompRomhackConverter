# Porting a romhack to Banjo: Recompiled

This guide turns a Banjo's Backpack romhack into a mod for [Banjo: Recompiled](https://github.com/BanjoRecomp/BanjoRecomp). The result is its own game mode, same as The Jiggies of Time and Nostalgia 64, and you also get a zip that's ready to upload to Thunderstore.

You don't need a compiler or any programming. The converter finds your romhack's code and has it recompiled, sets up Banjo: Recompiled's note saving for your levels, and packages everything.

## What you need

- The Banjo-Kazooie NTSC-U 1.0 (Rev 0) ROM, the same one Banjo: Recompiled uses. `.z64`, `.n64` and `.v64` all work.
- Your romhack, as the `.bps` patch you distribute or as the patched ROM. Use the `.bps` if you have it, since a patch made from the `.z64` ROM goes into the mod unchanged.
- `BKRecompRomhackTool.exe`, Wiseguy's tool that recompiles your romhack's code. It isn't included with the converter--see [First-time setup](#first-time-setup).
- Your own 256x256 `icon.png` and README text, for Thunderstore. A changelog and a separate in-game thumbnail are optional--without a thumbnail, the icon shows in the game's mod menu.

## First-time setup

Download the converter for your system from the [Releases](../../releases) page and unzip it anywhere then get BKRecompRomhackTool. Ask Wiseguy for a build, or build it yourself. On Windows:

1. Install [Visual Studio](https://visualstudio.microsoft.com/) Community with the **Desktop development with C++** workload, keeping **C++ CMake tools for Windows** ticked. You also need [Git](https://git-scm.com/).
2. Clone the tool with its submodules: `git clone --recurse-submodules https://github.com/Mr-Wiseguy/BKRecompRomhackTool`. GitHub's "Download ZIP" leaves the submodules out, so that copy won't build.
3. In Visual Studio, use **File > Open > Folder** on the cloned folder, wait for CMake to finish, then **Build > Build All**. The Output window shows where `BKRecompRomhackTool.exe` went, usually `out\build\x64-Debug\`.

On Linux or macOS, with Git, CMake and a C++ compiler:

```bash
git clone --recurse-submodules https://github.com/Mr-Wiseguy/BKRecompRomhackTool
cmake -S BKRecompRomhackTool -B BKRecompRomhackTool/build -DCMAKE_BUILD_TYPE=Release
cmake --build BKRecompRomhackTool/build
```

That leaves the tool at `BKRecompRomhackTool/build/BKRecompRomhackTool`. Either way, point the **BKRecompRomhackTool** field on the Files tab at it once, and saved projects remember where it is.

## Converting

Open `BKRecompRomhackConverter.exe` and work through the tabs. The gray examples under each field are from The Jiggies of Time.

1. On **Files**, choose the Banjo-Kazooie ROM, your romhack, `BKRecompRomhackTool.exe` and an output folder.
2. **Mod info** is what players see in Banjo: Recompiled's mod menu. The Mod ID is a permanent internal name, such as `bk_jiggies_of_time`. Banjo: Recompiled keeps the romhack's save file under it, so don't change it between versions. Keep the short description to a few words, since longer text gets cut off, and raise the version each time you release an update.
3. On **Notes**, click **Count notes from romhack**. The converter reads every map's setup, finds the notes you placed, and fills in the table. See [Note saving](#note-saving) for what to check.
4. **Thunderstore** needs a package name (letters, numbers and underscores only), a description of up to 250 characters, your `icon.png` and a README. Write the README and changelog in the boxes, or use **Import file...** for files you already have. To test the `.nrm` first, untick **Make a Thunderstore package** and come back to this tab later.
5. Click **Convert**. The output folder gets:
   - `<mod id>.nrm`: the mod itself.
   - `<package>-<version>.zip`: the Thunderstore package, if you made one.
   - `<mod id>_syms.toml`: a list of your romhack's code. You only need it if someone builds extra code changes for the mod later.

Use **File > Save project** to keep all of this. For an update, open the project (or drag it onto the converter), point it at the new `.bps`, raise the version and convert again.

## Testing

Drag the `.nrm` onto the Banjo: Recompiled window before starting a game, or use **Install Mods** in the mod menu. Enable the mod, then pick your romhack's game mode when starting.

## Note saving

Banjo: Recompiled can remember collected notes, which the original game doesn't. To do that it has to know how many notes each map has, and the Notes tab is where that goes.

Static notes are the ones you placed in a map. The converter counts these, so you shouldn't need to touch them.

Bundle notes come out of something else, such as the five notes a smashed hut drops in Mumbo's Mountain. The converter spots the vanilla note-dropping huts and placed note actors, but it can't know about notes your own code or other objects spawn. If your romhack has any, double-click the map's **Bundle notes** cell and add them.

Note saving tracks up to 256 notes per world, and only in the nine world slots (Mumbo's Mountain through Click Clock Wood). Notes in the lair, Spiral Mountain or other maps reset as in the original game. The converter tells you when that happens, and refuses to convert if a world has too many. If note saving causes problems for your romhack, untick **Support Banjo: Recompiled's note saving**.

Hidden actors are for signs or characters that tell the player notes reset when they leave a level, since that stops being true with note saving. List them to hide them while note saving is on: the actor ID, plus the type field if only some placements of that actor should go. FFFF means "any". For reference, these are what the existing mods hide:

| Romhack | Actor ID | Model ID | Type field |
|---|---|---|---|
| The Jiggies of Time | `0x0054` | `0x03EB` | `0xFFFF` |
| The Jiggies of Time (notes tutorial molehill) | `0x012B` | `0xFFFF` | `0x0008` |
| Nostalgia 64 | `0x0093` | `0x03A6` | `0xFFFF` |

## Publishing on Thunderstore

Sign in at [thunderstore.io](https://thunderstore.io), open the [Banjo: Recompiled community](https://thunderstore.io/c/banjo-recompiled/), and upload the `<package>-<version>.zip`. Thunderstore reads the name, version, description, README and icon from the zip.

## Limitations

This only handles romhacks whose code Backpack builds into one block loaded into expansion RAM. Romhacks whose extra code is compressed, or that load several code blocks, are rejected with a message saying so.

Some romhacks need fixes that only make sense on PC, beyond what every converted romhack gets. Those need a real mod build with the [mod template](https://github.com/BanjoRecomp/BKRecompModTemplate), and the `<mod id>_syms.toml` the converter writes is the starting point for that.
