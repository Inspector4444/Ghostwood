#!/usr/bin/env python3
"""
add_ow_sprite.py - register a new overworld (object event) sprite in a pokeemerald-expansion tree.

Does every edit from the "zombie overworld sprite addition" commit in one go:
  - copies the PNG into graphics/object_events/pics/people/
  - writes a JASC .pal from the PNG's palette (unless you reuse an existing palette tag)
  - include/constants/event_objects.h   : OBJ_EVENT_GFX_<X> (+ new OBJ_EVENT_PAL_TAG_<X>)
  - object_event_graphics.h              : INCGFX pic (+ pal)
  - object_event_pic_tables.h            : sPicTable_<X>
  - object_event_graphics_info.h         : gObjectEventGraphicsInfo_<X>
  - object_event_graphics_info_pointers.h: extern + table entry
  - src/event_object_movement.c          : sObjectEventSpritePalettes entry (new palettes only)

Safe to re-run: every step is skipped if its marker is already present.

Usage (from the repo root):
  python3 tools/add_ow_sprite.py zombie_woman path/to/zombie_woman.png
  python3 tools/add_ow_sprite.py zombie_woman --palette-tag OBJ_EVENT_PAL_TAG_ZOMBIEMAN   # share a palette
  python3 tools/add_ow_sprite.py zombie_woman path/to/png --dry-run                       # preview only

The PNG must be the standard 9-frame NPC sheet (frames side by side), indexed, <= 16 colors:
  16x16 frames -> 144x16,  16x32 frames -> 144x32,  32x32 frames -> 288x32.
Needs Pillow only when it has to write a .pal (pip install pillow).
"""
import argparse
import filecmp
import re
import shutil
import sys
from pathlib import Path

FRAMES = 9

# frame size -> (oam base, subsprite tables, byte size per frame, default shadow)
SIZES = {
    (16, 16): ("gObjectEventBaseOam_16x16", "sOamTables_16x16", 256, "SHADOW_SIZE_M"),
    (16, 32): ("gObjectEventBaseOam_16x32", "sOamTables_16x32", 512, "SHADOW_SIZE_M"),
    (32, 32): ("gObjectEventBaseOam_32x32", "sOamTables_32x32", 1024, "SHADOW_SIZE_L"),
}

PATHS = {
    "constants": "include/constants/event_objects.h",
    "gfx": "src/data/object_events/object_event_graphics.h",
    "pics": "src/data/object_events/object_event_pic_tables.h",
    "info": "src/data/object_events/object_event_graphics_info.h",
    "ptrs": "src/data/object_events/object_event_graphics_info_pointers.h",
    "move": "src/event_object_movement.c",
}
PIC_DIR = "graphics/object_events/pics/people"
PAL_DIR = "graphics/object_events/palettes"


class Tree:
    def __init__(self, root, dry):
        self.root, self.dry, self.cache, self.log = Path(root), dry, {}, []

    def read(self, key):
        if key not in self.cache:
            p = self.root / PATHS[key]
            if not p.exists():
                sys.exit(f"error: {p} not found (run from the repo root, or pass --root)")
            self.cache[key] = p.read_text(encoding="utf-8")
        return self.cache[key]

    def write(self, key, text, what):
        self.cache[key] = text
        self.log.append(f"  edit  {PATHS[key]}: {what}")

    def flush(self):
        if self.dry:
            return
        for key, text in self.cache.items():
            (self.root / PATHS[key]).write_text(text, encoding="utf-8")


def camel(snake):
    return "".join(p.capitalize() for p in snake.split("_"))


def insert_before_regex(text, pattern, new_line):
    m = re.search(pattern, text, re.M)
    if not m:
        return None
    return text[: m.start()] + new_line + "\n" + text[m.start():]


def append(text, block):
    if not text.endswith("\n"):
        text += "\n"
    return text + "\n" + block + "\n"


def make_pal(png_path, pal_path):
    try:
        from PIL import Image
    except ImportError:
        sys.exit("error: Pillow is needed to write the .pal (pip install pillow), "
                 "or reuse an existing palette with --palette-tag")
    im = Image.open(png_path)
    if im.mode != "P":
        sys.exit(f"error: {png_path} is not an indexed PNG (mode {im.mode}); convert it to 16 colors first")
    raw = im.getpalette() or []
    colors = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    used = max(im.tobytes()) + 1 if im.width * im.height else 0   # mode P: one index byte per pixel
    if used > 16:
        sys.exit(f"error: {png_path} uses {used} palette entries; object events allow 16")
    colors = (colors + [(0, 0, 0)] * 16)[:16]
    pal_path.write_text("JASC-PAL\n0100\n16\n" + "\n".join(f"{r} {g} {b}" for r, g, b in colors) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="snake_case sprite name, e.g. zombie_woman")
    ap.add_argument("png", nargs="?", help="source PNG (default: graphics/object_events/pics/people/<name>.png)")
    ap.add_argument("--root", default=".", help="repo root (default: current directory)")
    ap.add_argument("--cname", help="CamelCase symbol name (default: derived from name)")
    ap.add_argument("--palette-tag", help="reuse an existing OBJ_EVENT_PAL_TAG_* instead of making a new palette")
    ap.add_argument("--palette-slot", default="PALSLOT_NPC_1", help="default PALSLOT_NPC_1")
    ap.add_argument("--reflection-tag", default="OBJ_EVENT_PAL_TAG_BRIDGE_REFLECTION")
    ap.add_argument("--shadow", help="override shadow size, e.g. SHADOW_SIZE_S")
    ap.add_argument("--tracks", default="TRACKS_FOOT")
    ap.add_argument("--zombie", action="store_true", help="also print the sZombieLooks line to paste")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    name = a.name.lower()
    cname = a.cname or camel(name)
    upper = name.upper()
    gfx_const = f"OBJ_EVENT_GFX_{upper}"
    root = Path(a.root)
    t = Tree(root, a.dry_run)

    # ---- png + size ----
    dest_png = root / PIC_DIR / f"{name}.png"
    src_png = Path(a.png) if a.png else dest_png
    if not src_png.exists():
        sys.exit(f"error: {src_png} not found")
    try:
        from PIL import Image
        with Image.open(src_png) as im:
            w, h = im.size
    except ImportError:
        sys.exit("error: Pillow is needed to read the PNG size (pip install pillow)")
    if w % FRAMES:
        sys.exit(f"error: PNG is {w}px wide; expected {FRAMES} frames side by side")
    fw, fh = w // FRAMES, h
    if (fw, fh) not in SIZES:
        sys.exit(f"error: frame size {fw}x{fh} not supported (use one of {sorted(SIZES)})")
    oam, subs, size, shadow = SIZES[(fw, fh)]
    shadow = a.shadow or shadow
    tw, th = fw // 8, fh // 8

    # ---- palette ----
    new_palette = a.palette_tag is None
    pal_tag = a.palette_tag or f"OBJ_EVENT_PAL_TAG_{upper}"
    consts = t.read("constants")
    if not new_palette and pal_tag not in consts:
        sys.exit(f"error: {pal_tag} not found in {PATHS['constants']}")

    # ---- 1. files ----
    if src_png.resolve() == dest_png.resolve() or (dest_png.exists() and filecmp.cmp(src_png, dest_png, shallow=False)):
        t.log.append(f"  skip  {PIC_DIR}/{name}.png already in place")
    else:
        t.log.append(f"  copy  {src_png} -> {PIC_DIR}/{name}.png")
        if not a.dry_run:
            dest_png.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_png, dest_png)
    pal_path = root / PAL_DIR / f"{name}.pal"
    if new_palette:
        if pal_path.exists():
            t.log.append(f"  skip  {PAL_DIR}/{name}.pal already exists (delete it to regenerate)")
        else:
            t.log.append(f"  write {PAL_DIR}/{name}.pal (from the PNG's palette)")
            if not a.dry_run:
                make_pal(dest_png if dest_png.exists() else src_png, pal_path)

    # ---- 2. constants ----
    if gfx_const in consts:
        t.log.append(f"  skip  {gfx_const} already defined")
    else:
        new = insert_before_regex(consts, r"^\s*NUM_OBJ_EVENT_GFX,", f"    {gfx_const},")
        if new is None:
            sys.exit("error: couldn't find NUM_OBJ_EVENT_GFX in the constants header")
        consts = new
        t.write("constants", consts, f"added {gfx_const}")
    if new_palette:
        if re.search(rf"#define\s+{pal_tag}\b", consts):
            t.log.append(f"  skip  {pal_tag} already defined")
        else:
            tags = [(int(m.group(2), 16), m.end())
                    for m in re.finditer(r"#define\s+(OBJ_EVENT_PAL_TAG_\w+)\s+0x([0-9A-Fa-f]+)", consts)
                    if int(m.group(2), 16) < 0x11FF]   # 0x11FF is OBJ_EVENT_PAL_TAG_NONE
            top, end = max(tags)
            line_end = consts.index("\n", end)
            define = f"#define {pal_tag}".ljust(50)   # matches the existing column
            consts = consts[:line_end] + f"\n{define}0x{top + 1:04X}" + consts[line_end:]
            t.write("constants", consts, f"added {pal_tag} = 0x{top + 1:04X}")

    # ---- 3. graphics / pic table / info ----
    gfx = t.read("gfx")
    if f"gObjectEventPic_{cname}[]" in gfx:
        t.log.append(f"  skip  gObjectEventPic_{cname} already exists")
    else:
        block = (f'const u32 gObjectEventPic_{cname}[] = INCGFX_U32("{PIC_DIR}/{name}.png", ".4bpp", '
                 f'"-mwidth {tw} -mheight {th}");')
        if new_palette:
            block += f'\nconst u16 gObjectEventPal_{cname}[] = INCGFX_U16("{PAL_DIR}/{name}.pal", ".gbapal");'
        t.write("gfx", append(gfx, block), "added pic" + (" + pal" if new_palette else ""))

    pics = t.read("pics")
    if f"sPicTable_{cname}[]" in pics:
        t.log.append(f"  skip  sPicTable_{cname} already exists")
    else:
        block = (f"static const struct SpriteFrameImage sPicTable_{cname}[] = {{\n"
                 f"    overworld_ascending_frames(gObjectEventPic_{cname}, {tw}, {th}),\n}};")
        t.write("pics", append(pics, block), f"added sPicTable_{cname}")

    info = t.read("info")
    if f"gObjectEventGraphicsInfo_{cname} " in info:
        t.log.append(f"  skip  gObjectEventGraphicsInfo_{cname} already exists")
    else:
        block = f"""const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_{cname} = {{
    .tileTag = TAG_NONE,
    .paletteTag = {pal_tag},
    .reflectionPaletteTag = {a.reflection_tag},
    .size = {size},
    .width = {fw},
    .height = {fh},
    .paletteSlot = {a.palette_slot},
    .shadowSize = {shadow},
    .inanimate = FALSE,
    .compressed = FALSE,
    .tracks = {a.tracks},
    .oam = &{oam},
    .subspriteTables = {subs},
    .anims = sAnimTable_Standard,
    .images = sPicTable_{cname},
}};"""
        t.write("info", append(info, block), f"added gObjectEventGraphicsInfo_{cname}")

    # ---- 4. pointers ----
    ptrs = t.read("ptrs")
    if f"gObjectEventGraphicsInfo_{cname};" in ptrs:
        t.log.append(f"  skip  pointer entries for {cname} already exist")
    else:
        extern = f"extern const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_{cname};"
        new = insert_before_regex(ptrs, r"^// Begin Pok.mon event objects", extern)
        if new is None:
            sys.exit("error: couldn't find the '// Begin Pokemon event objects' anchor in the pointers header")
        ptrs = new
        m = re.search(r"gObjectEventGraphicsInfoPointers\[[^\]]*\]\s*=\s*\{", ptrs)
        if not m:
            sys.exit("error: couldn't find gObjectEventGraphicsInfoPointers[]")
        close = re.compile(r"^\};", re.M).search(ptrs, m.end())
        if not close:
            sys.exit("error: couldn't find the end of gObjectEventGraphicsInfoPointers[]")
        entry = f"    [{gfx_const}]".ljust(45) + f"= &gObjectEventGraphicsInfo_{cname},\n"
        ptrs = ptrs[: close.start()] + entry + ptrs[close.start():]
        t.write("ptrs", ptrs, "added extern + table entry")

    # ---- 5. palette list ----
    if new_palette:
        mv = t.read("move")
        if f"gObjectEventPal_{cname}," in mv:
            t.log.append("  skip  sObjectEventSpritePalettes entry already exists")
        else:
            m = re.search(r"static const struct SpritePalette sObjectEventSpritePalettes\[\]\s*=\s*\{\n", mv)
            if not m:
                sys.exit("error: couldn't find sObjectEventSpritePalettes[] in event_object_movement.c")
            entry = f"    {{gObjectEventPal_{cname},".ljust(44) + f"{pal_tag}}},\n"
            t.write("move", mv[: m.end()] + entry + mv[m.end():], "added palette entry")

    t.flush()
    print(("[dry run] " if a.dry_run else "") + f"{name} -> {gfx_const}  ({fw}x{fh}, palette {pal_tag})")
    print("\n".join(t.log))
    print(f"\nUse it in map.json as:  \"graphics_id\": \"{gfx_const}\"")
    if a.zombie:
        print(f"For zombies, add to sZombieLooks (src/data/zombie_hordes.h):\n"
              f"    {{ .gfxId = {gfx_const}, .trainerA = TRAINER_ZOMBIE_A, .trainerB = TRAINER_ZOMBIE_B }},")


if __name__ == "__main__":
    main()
