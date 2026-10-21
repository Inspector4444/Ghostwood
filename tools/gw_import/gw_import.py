#!/usr/bin/env python3
"""gw_import - pull m4a voicegroups (samples, square/wave/noise voices, keysplits)
out of a GBA ROM into a pokeemerald repo, in the repo's own layout and macros.

  gw_import.py banks  rom.gba [--songtable 0x...]
  gw_import.py list   rom.gba --voicegroup 0x... [--only 0-9,12] [--deep]
  gw_import.py import rom.gba --voicegroup 0x... --name gw_foo [--only ...] [--repo .]

Run `import` from the repo root (or pass --repo). Re-running with --force replaces
exactly what the previous run of the same --name added.
"""
import argparse
import re
import sys
from pathlib import Path

from rom import Rom, RomError, parse_addr, find_song_table, list_song_banks
from voices import read_voice, adsr
from emit import Importer, put_block, vanilla_waves, migrate_legacy


def parse_index_list(text):
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out += range(int(a, 0), int(b, 0) + 1)
        else:
            out.append(int(part, 0))
    for i in out:
        if not 0 <= i < 128:
            sys.exit(f"voice index {i} out of range 0-127")
    return out


def build_slots(rom, args):
    vg = parse_addr(args.voicegroup)
    if not rom.ptr_ok(0x08000000 | vg, 12):
        sys.exit(f"voicegroup 0x{vg:X} is outside the ROM")

    def at(i):
        return read_voice(rom, vg + 12 * i)

    slots = [None] * 128
    mapping = []
    if getattr(args, "map", None):
        for part in args.map.split(","):
            dst, src = (int(x, 0) for x in part.split("="))
            if not (0 <= dst < 128 and 0 <= src < 4096):
                sys.exit(f"bad --map entry {part}")
            slots[dst] = at(src)
            mapping.append((src, dst))
    elif args.only:
        for i in parse_index_list(args.only):
            slots[i] = at(i)
            mapping.append((i, i))
    else:
        for i in range(min(args.count, 128)):
            slots[i] = at(i)
    return vg, slots, mapping


def print_table(imp, slots, deep=False):
    print(f"{'idx':>3}  {'type':<5} {'kind':<9} {'key':>3} {'len':>3} {'ps':>4}  {'ADSR':<15} detail")
    for i, v in enumerate(slots):
        if v is None:
            continue
        kind, detail = imp.describe(v)
        if kind in ("empty", "unused"):
            continue
        a = "-" if kind in ("keysplit", "rhythm") else "%d,%d,%d,%d" % adsr(v)
        print(f"{i:>3}  0x{v.type:02x}  {kind:<9} {v.key:>3} {v.length:>3} 0x{v.pan_sweep:02x}  {a:<15} {detail}")
        if deep and kind in ("keysplit", "rhythm"):
            base = Rom.to_off(v.w1)
            idxs = imp.split_indices(v) if kind == "keysplit" else range(128)
            for j in idxs:
                sv = read_voice(imp.rom, base + 12 * j)
                k2, d2 = imp.describe(sv, True)
                if k2 in ("empty", "unused", "invalid"):
                    continue
                print(f"       -> {j:>3}  0x{sv.type:02x}  {k2:<9} {sv.key:>3} {sv.length:>3} 0x{sv.pan_sweep:02x}  {'%d,%d,%d,%d' % adsr(sv):<15} {d2}")


def cmd_banks(args):
    rom = Rom(args.rom)
    table = parse_addr(args.songtable) if args.songtable else find_song_table(rom)
    if table is None:
        sys.exit("no m4a song table found - pass --songtable (the ripper prints it as 'Song table located at')")
    songs = list_song_banks(rom, table)
    print(f"song table @0x{table:06X}, {len(songs)} songs")
    banks = {}
    for idx, _, vg in songs:
        if vg is not None:
            banks.setdefault(vg, []).append(idx)
    for vg, idxs in sorted(banks.items()):
        shown = ",".join(map(str, idxs[:12])) + ("..." if len(idxs) > 12 else "")
        print(f"  voicegroup @0x{vg:06X}  used by {len(idxs):>3} songs  ({shown})")


def cmd_list(args):
    rom = Rom(args.rom)
    vg, slots, _ = build_slots(rom, args)
    print(f"voicegroup @0x{vg:06X}")
    print_table(Importer(rom, "preview"), slots, args.deep)


REGISTRY = ("sound/direct_sound_data.inc", "sound/programmable_wave_data.inc",
            "sound/keysplit_tables.inc", "sound/voice_groups.inc")


def cmd_import(args):
    name = args.name if args.name.startswith("gw_") else "gw_" + args.name
    if not re.fullmatch(r"gw_[a-z0-9_]+", name):
        sys.exit("--name must be lowercase letters, digits, underscores")
    repo = Path(args.repo)
    for rel in ("sound/voice_groups.inc", "sound/direct_sound_data.inc"):
        if not (repo / rel).is_file():
            sys.exit(f"{rel} not found under {repo.resolve()} - run from your repo root or pass --repo")
    top = repo / "sound/voicegroups" / f"{name}.inc"
    if top.exists() and not args.force:
        sys.exit(f"{top} exists (use --force to overwrite)")

    rom = Rom(args.rom)
    vg, slots, mapping = build_slots(rom, args)
    imp = Importer(rom, name, "bin" if args.bin else args.format, vanilla_waves(repo))
    out = imp.build(slots)
    for rel in REGISTRY[1:3]:
        if out.blocks[rel] and not (repo / rel).is_file():
            sys.exit(f"this import needs {rel}, which does not exist in {repo.resolve()}")

    removed = migrate_legacy(repo, name)
    for rel, text in out.files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    notes = imp.write_assets(repo)
    for rel in REGISTRY:
        put_block(repo / rel, name, out.blocks[rel])

    n_ks = sum(1 for r in out.files if "/keysplits/" in r)
    n_dr = sum(1 for r in out.files if "/drumsets/" in r)
    kib = sum(s.length for _, _, s in imp._by_digest.values()) / 1024
    print(f"imported voicegroup @0x{vg:06X} as '{name}'")
    for line in removed:
        print(f"  cleanup     : {line}")
    print(f"  voicegroup  : sound/voicegroups/{name}.inc  (+{n_ks} keysplit, {n_dr} drumset groups)")
    print(f"  samples     : {len(imp._by_digest)} in sound/direct_sound_samples/{name}/  (~{kib:.0f} KiB uncompressed)")
    print(f"  waves       : {len(imp.waves)} new, {len(imp.reused_waves)} reused from existing ProgrammableWaveData_*")
    print(f"  registered  : {', '.join(r.split('/')[-1] for r in REGISTRY if out.blocks[r])}")
    for n in notes:
        print(f"  sample note : {n}")
    for w in sorted(set(imp.warnings)):
        print(f"  warning     : top-level voice dropped ({w})")
    if mapping and any(a != b for a, b in mapping):
        print("  remap       : source -> new slot: " + ", ".join(f"{a}->{b}" for a, b in mapping))
    print(f"  midi.cfg    : -G_{name}   (check an existing line in sound/songs/midi/midi.cfg for the -G style)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("banks", help="list voicegroups used by the ROM's songs")
    b.add_argument("rom")
    b.add_argument("--songtable")
    b.set_defaults(fn=cmd_banks)

    def common(p):
        p.add_argument("rom")
        p.add_argument("--voicegroup", required=True, help="ROM offset or 0x08xxxxxx address")
        p.add_argument("--count", type=int, default=128)
        p.add_argument("--only", help="keep only these voice indexes in their original slots, e.g. 0-9,12")
        p.add_argument("--map", help="DST=SRC,... place source voices in chosen slots (cherry-pick)")

    l = sub.add_parser("list", help="dry run: print the voice table")
    common(l)
    l.add_argument("--deep", action="store_true", help="also list keysplit/rhythm sub-voices")
    l.set_defaults(fn=cmd_list)

    i = sub.add_parser("import", help="write voicegroups + samples into a repo")
    common(i)
    i.add_argument("--name", required=True, help="import name; gets a gw_ prefix, namespaces every label and file")
    i.add_argument("--repo", default=".")
    i.add_argument("--format", choices=("wav", "aif"), default="wav",
                   help="sample source format: wav for pokeemerald-expansion (wav2agb, default), aif for vanilla (aif2pcm)")
    i.add_argument("--bin", action="store_true", help="write exact .bin samples (keeps BDPCM, no build step) instead")
    i.add_argument("--force", action="store_true", help="overwrite an earlier import of the same name")
    i.add_argument("--number", help=argparse.SUPPRESS)   # no longer needed, accepted for old command lines
    i.add_argument("--hook", action="store_true", help=argparse.SUPPRESS)
    i.set_defaults(fn=cmd_import)

    args = ap.parse_args()
    try:
        args.fn(args)
    except RomError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
