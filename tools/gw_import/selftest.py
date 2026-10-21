#!/usr/bin/env python3
"""Synthetic-ROM selftest:  python3 tools/gw_import/selftest.py

Builds a fake ROM covering every voice type and a fake repo shaped like pokeemerald
(including leftovers from the first version of this tool), imports, then checks the
layout, idempotency, migration and wave reuse. If binutils is present it also assembles
the generated files with stand-in voice_* macros, checks for undefined symbols, and
compares every emitted voice's bytes against the source ROM.
"""
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from samples import LUT, read_sample  # noqa: E402
from rom import Rom  # noqa: E402
from emit import Importer  # noqa: E402
from voices import read_voice  # noqa: E402

G = 0x08000000
WAVE_A = bytes.fromhex("00112233445566778899aabbccddeeff")   # also "vanilla" 01.pcm -> must be reused
WAVE_B = bytes([0xFF, 0x00] * 8)                               # new


def voice(t, key, ln, ps, w1, w2):
    return struct.pack("<BBBBII", t, key, ln, ps, w1, w2)


def adsr(a, d, s, r):
    return a | d << 8 | s << 16 | r << 24


def bdpcm_encode(pcm):
    out = bytearray()
    for b in range(0, len(pcm), 64):
        blk = pcm[b:b + 64]
        acc = blk[0]
        out.append(acc & 0xFF)
        nibs = []
        for x in blk[1:]:
            best = min(range(16), key=lambda n: abs(((acc + LUT[n] + 128) & 0xFF) - 128 - x))
            acc = ((acc + LUT[best] + 128) & 0xFF) - 128
            nibs.append(best)
        nibs.append(0)
        for i in range(0, 64, 2):
            out.append(nibs[i] << 4 | nibs[i + 1])
    return bytes(out)


N_TOP = 16


def build_rom():
    rom = bytearray(0x8000)

    def put(off, data):
        rom[off:off + len(data)] = data

    sine = [int(60 * math.sin(2 * math.pi * i / 64)) for i in range(64)]
    put(0x2000, struct.pack("<IIII", 0x40000000, 22050 << 10, 8, 64) + bytes(x & 0xFF for x in sine))
    put(0x2100, struct.pack("<IIII", 1, 13379 << 10, 0, 64) + bdpcm_encode(sine))
    put(0x3000, WAVE_A)
    put(0x3010, WAVE_B)
    put(0x4000, voice(0, 60, 0, 0, G | 0x2000, adsr(255, 0, 255, 165))
        + voice(0, 60, 0, 0, G | 0x2000, adsr(200, 10, 200, 100))
        + voice(2, 60, 0, 0, 2, adsr(0, 0, 15, 0)))
    # realistic key table: real range 36-108, neighbours' bytes before (3s) and after (0s)
    put(0x5000, bytes([3] * 36 + [0] * 35 + [1] * 21 + [2] * 17 + [0] * 19))
    put(0x6000 + 12 * 36, voice(4, 60, 0, 0, 1, adsr(0, 1, 5, 1)))
    put(0x6000 + 12 * 37, voice(0, 60, 0, 0xC0, G | 0x2000, adsr(255, 0, 255, 100)))
    top = [
        voice(0, 60, 0, 0, G | 0x2000, adsr(255, 0, 255, 165)),      # 0 direct
        voice(0x08, 60, 0, 0, G | 0x2100, adsr(255, 0, 255, 165)),   # 1 direct fixed, BDPCM
        voice(1, 60, 0, 0x04, 1, adsr(0, 1, 15, 2)),                 # 2 square1 + sweep
        voice(2, 60, 0, 0, 3, adsr(0, 2, 12, 1)),                    # 3 square2
        voice(3, 60, 0, 0, G | 0x3000, adsr(0, 0, 15, 0)),          # 4 wave (== vanilla 01.pcm)
        voice(4, 60, 0, 0, 0, adsr(0, 1, 8, 2)),                     # 5 noise
        voice(0x40, 0, 0, 0, G | 0x4000, G | 0x5000),                # 6 keysplit
        voice(0x80, 0, 0, 0, G | 0x6000, 0),                         # 7 rhythm
        voice(1, 0x3C, 0, 0, 2, 0x0F0000),                           # 8 unused marker
        voice(0, 60, 0, 0, G | 0x7F00, 0),                           # 9 bad sample -> filler
        voice(0x10, 60, 0, 0, G | 0x2000, adsr(255, 0, 255, 100)),   # 10 reverse direct -> raw
        voice(1, 60, 0, 0xC0, 2, adsr(0, 1, 15, 2)),                 # 11 square1 with pan
        voice(0, 60, 0, 0xC0, G | 0x2000, adsr(255, 0, 255, 100)),   # 12 direct with pan
        voice(0x0C, 60, 0, 0, 0x1000000, adsr(0, 1, 8, 2)),          # 13 noise alt, metallic
        voice(2, 60, 5, 0, 1, adsr(0, 1, 8, 2)),                     # 14 square2 with length -> raw
        voice(3, 60, 0, 0, G | 0x3010, adsr(0, 0, 15, 0)),          # 15 wave (new)
    ]
    assert len(top) == N_TOP
    put(0x0100, b"".join(top))
    return bytes(rom), sine


def run(args, expect_ok=True):
    r = subprocess.run([sys.executable, str(HERE / "gw_import.py"), *args], capture_output=True, text=True)
    print(r.stdout, end="")
    if (r.returncode == 0) != expect_ok:
        print(r.stderr)
        sys.exit("FAILED: " + " ".join(args))
    return r.stdout


def make_repo(root):
    def w(rel, text, mode="w"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        (p.write_bytes if mode == "wb" else p.write_text)(text)

    w("sound/voice_groups.inc", '.include "sound/voicegroups/dummy.inc"\n\n@Custom\n\n.include "sound/voicegroups/emerald_universal.inc"')
    w("sound/voicegroups/dummy.inc", "voice_group dummy\n" + "    voice_square_1 60, 0, 0, 2, 0, 0, 15, 0\n" * 128)
    w("sound/voicegroups/emerald_universal.inc", "voice_group emerald_universal\n" + "    voice_square_1 60, 0, 0, 2, 0, 0, 15, 0\n" * 128)
    w("sound/direct_sound_data.inc", '\t.align 2\nDirectSoundWaveData_vanilla::\n\t.incbin "sound/direct_sound_samples/vanilla.bin"\n')
    w("sound/programmable_wave_data.inc", '\t.align 2\nProgrammableWaveData_1::\n\t.incbin "sound/programmable_wave_samples/01.pcm"\n')
    w("sound/programmable_wave_samples/01.pcm", WAVE_A, "wb")
    w("sound/keysplit_tables.inc", "@ comment\nkeysplit piano, 36\nsplit 0, 55\nsplit 1, 70\nsplit 2, 91\nsplit 3, 108\n")
    # leftovers of the first version of the tool
    w("data/sound_data.s", '\t.include "sound/voice_groups.inc"\n\t.include "sound/ghostwood/ghostwood_sound.inc"\n\t.include "sound/cry_tables.inc"\n')
    w("sound/ghostwood/ghostwood_sound.inc", "old")
    w("sound/ghostwood/gw_voice_macros.inc", "old")
    w("sound/ghostwood/imports/gw_test.inc", "old")
    w("sound/ghostwood/imports/gw_test.report.txt", "old")
    w("sound/direct_sound_samples/ghostwood/gw_test/gw_test_002000.wav", b"old", "wb")


MACROS = """
.macro voice_group name, offset=0
	.align 2
voicegroup_\\name:
.endm
.macro _pan pan, other
	.if \\pan != 0
	.byte (0x80 | \\pan)
	.else
	.byte \\other
	.endif
.endm
.macro _voice type, key, pan, sweep, w1, a, d, s, r
	.byte \\type, \\key, 0x0
	_pan \\pan, \\sweep
	.4byte \\w1
	.byte \\a, \\d, \\s, \\r
.endm
.macro voice_directsound k, p, w, a, d, s, r
	_voice 0x0, \\k, \\p, 0, \\w, \\a, \\d, \\s, \\r
.endm
.macro voice_directsound_no_resample k, p, w, a, d, s, r
	_voice 0x8, \\k, \\p, 0, \\w, \\a, \\d, \\s, \\r
.endm
.macro voice_square_1 k, p, sweep, duty, a, d, s, r
	_voice 0x1, \\k, \\p, \\sweep, \\duty, \\a, \\d, \\s, \\r
.endm
.macro voice_square_1_alt k, p, sweep, duty, a, d, s, r
	_voice 0x9, \\k, \\p, \\sweep, \\duty, \\a, \\d, \\s, \\r
.endm
.macro voice_square_2 k, p, duty, a, d, s, r
	_voice 0x2, \\k, \\p, 0, \\duty, \\a, \\d, \\s, \\r
.endm
.macro voice_square_2_alt k, p, duty, a, d, s, r
	_voice 0xA, \\k, \\p, 0, \\duty, \\a, \\d, \\s, \\r
.endm
.macro voice_programmable_wave k, p, w, a, d, s, r
	_voice 0x3, \\k, \\p, 0, \\w, \\a, \\d, \\s, \\r
.endm
.macro voice_programmable_wave_alt k, p, w, a, d, s, r
	_voice 0xB, \\k, \\p, 0, \\w, \\a, \\d, \\s, \\r
.endm
.macro voice_noise k, p, period, a, d, s, r
	_voice 0x4, \\k, \\p, 0, \\period, \\a, \\d, \\s, \\r
.endm
.macro voice_noise_alt k, p, period, a, d, s, r
	_voice 0xC, \\k, \\p, 0, \\period, \\a, \\d, \\s, \\r
.endm
.macro keysplit name, offset
	.set keysplit_\\name, . - \\offset
	.set _ks_next, \\offset
.endm
.macro split voice, last
	.fill \\last - _ks_next + 1, 1, \\voice
	.set _ks_next, \\last + 1
.endm
.macro voice_keysplit grp, table
	.byte 0x40, 0, 0, 0
	.4byte \\grp
	.4byte \\table
.endm
.macro voice_keysplit_all grp
	.byte 0x80, 0, 0, 0
	.4byte \\grp
	.4byte 0
.endm
"""


def assemble_check(repo, rom_bytes, rom_path):
    if not all(shutil.which(t) for t in ("as", "nm", "objcopy")):
        print("(binutils not found, skipping assemble check)")
        return
    work = repo.parent / "asm"
    shutil.copytree(repo / "sound", work / "sound")
    for p in (work / "sound").rglob("*"):
        if p.suffix in (".inc", ".s"):
            # x86 gas stand-in: drop ARM '@' comments and the ARM-only 'label::' form
            p.write_text(re.sub(r"::", ":", re.sub(r"@.*", "", p.read_text())))
    for p in (work / "sound").rglob("*.inc"):
        for m in re.finditer(r'\.incbin\s+"([^"]+)"', p.read_text()):
            f = work / m.group(1)
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b"\0" * 16)
    (work / "macros.s").write_text(MACROS)
    (work / "main.s").write_text(
        '.include "macros.s"\n.include "sound/voice_groups.inc"\n.include "sound/direct_sound_data.inc"\n'
        '.include "sound/programmable_wave_data.inc"\n.include "sound/keysplit_tables.inc"\n')
    r = subprocess.run(["as", "-I", ".", "-o", "main.o", "main.s"], cwd=work, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    syms = subprocess.run(["nm", "main.o"], cwd=work, capture_output=True, text=True).stdout.split("\n")
    undefined = [l for l in syms if l.split()[:1] == ["U"] or (len(l.split()) == 2 and l.split()[0] == "U")]
    assert not undefined, undefined
    subprocess.run(["objcopy", "-O", "binary", "-j", ".text", "main.o", "main.bin"], cwd=work, check=True)
    blob = (work / "main.bin").read_bytes()
    addr = {l.split()[2]: int(l.split()[0], 16) for l in syms if len(l.split()) == 3}
    base = addr["voicegroup_gw_test"]
    rom = Rom(rom_path)
    imp = Importer(rom, "x")
    filler = bytes([1, 0x3C, 0, 0, 2, 0, 0, 0, 0, 0, 15, 0])
    for i in range(N_TOP):
        got = blob[base + 12 * i: base + 12 * i + 12]
        v = read_voice(rom, 0x100 + 12 * i)
        exp = rom_bytes[0x100 + 12 * i: 0x100 + 12 * i + 12]
        kind, _ = imp.resolve(v, False)
        if kind in ("empty", "unused", "invalid"):
            assert got == filler, (i, kind, got.hex())
        elif kind in ("keysplit", "rhythm"):
            assert got[:4] == exp[:4], (i, got.hex(), exp.hex())
        else:
            assert got[:4] == exp[:4] and got[8:] == exp[8:], (i, kind, got.hex(), exp.hex())
            if kind in ("square1", "square2", "noise"):
                assert got[4:8] == exp[4:8], (i, kind)
    for need in ("voicegroup_gw_test_keysplit_004000", "voicegroup_gw_test_drumset_006000", "keysplit_gw_test_005000"):
        assert need in addr, need
    ks = addr["keysplit_gw_test_005000"]          # label sits 36 bytes before the data
    for key in range(36, 109):
        assert blob[ks + key] == rom_bytes[0x5000 + key], key
    print(f"assemble check OK ({N_TOP} top voices byte-compared, no undefined symbols)")


def main():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        rom_bytes, sine = build_rom()
        rom_path = td / "fake.gba"
        rom_path.write_bytes(rom_bytes)
        repo = td / "repo"
        make_repo(repo)

        out = run(["list", str(rom_path), "--voicegroup", "0x100", "--count", str(N_TOP), "--deep"])
        for needle in ("direct", "square1", "square2", "wave", "noise", "keysplit", "rhythm", "BDPCM"):
            assert needle in out, f"list output missing {needle}"

        base = ["import", str(rom_path), "--voicegroup", "0x100", "--count", str(N_TOP), "--name", "gw_test", "--repo", str(repo)]
        out = run(base)
        run(base + ["--force"])                      # re-run must be idempotent
        run(base, expect_ok=False)                   # and refuse without --force

        # layout
        vgtext = (repo / "sound/voicegroups/gw_test.inc").read_text()
        assert vgtext.startswith("voice_group gw_test\n")
        assert "voice_directsound 60, 0, DirectSoundWaveData_gw_test_002000, 255, 0, 255, 165" in vgtext
        assert "voice_directsound_no_resample 60, 0, DirectSoundWaveData_gw_test_002100" in vgtext
        assert "voice_square_1 60, 0, 4, 1, 0, 1, 15, 2" in vgtext
        assert "voice_square_1 60, 64, 0, 2, 0, 1, 15, 2" in vgtext          # pan decoded from 0xC0
        assert "voice_directsound 60, 64, DirectSoundWaveData_gw_test_002000" in vgtext
        assert "voice_noise_alt 60, 0, 16777216" in vgtext
        assert "voice_programmable_wave 60, 0, ProgrammableWaveData_1," in vgtext   # reused vanilla wave
        assert "ProgrammableWaveData_gw_test_" in vgtext                           # new wave
        assert ".byte 0x10, 60, 0, 0x00" in vgtext and ".byte 0x02, 60, 5, 0x00" in vgtext   # raw fallbacks
        assert "voice_keysplit voicegroup_gw_test_keysplit_004000, keysplit_gw_test_005000" in vgtext
        assert "voice_keysplit_all voicegroup_gw_test_drumset_006000" in vgtext
        assert vgtext.count("\n") == 129 + 2 * 2         # header + 128 voices + 2 raw voices x 2 extra lines
        assert (repo / "sound/voicegroups/keysplits/gw_test_004000.inc").read_text().count("\n") == 4   # header + 3 voices, no stray ones
        ksb = (repo / "sound/keysplit_tables.inc").read_text()
        assert "keysplit gw_test_005000, 36\nsplit 0, 70\nsplit 1, 91\nsplit 2, 108\n" in ksb, ksb
        assert (repo / "sound/voicegroups/drumsets/gw_test_006000.inc").is_file()
        wavs = sorted((repo / "sound/direct_sound_samples/gw_test").glob("*.wav"))
        assert len(wavs) == 2, wavs                       # deduplicated
        for w in wavs:
            d = w.read_bytes()
            assert d[:4] == b"RIFF" and d[8:12] == b"WAVE" and b"smpl" in d
        new_pcm = list((repo / "sound/programmable_wave_samples").glob("gw_test_*.pcm"))
        assert len(new_pcm) == 1 and new_pcm[0].read_bytes() == WAVE_B

        # registry blocks: exactly one each, vanilla content untouched
        for rel in ("sound/voice_groups.inc", "sound/direct_sound_data.inc",
                    "sound/programmable_wave_data.inc", "sound/keysplit_tables.inc"):
            t = (repo / rel).read_text()
            assert t.count("@ gw_import:begin gw_test") == 1 and t.count("@ gw_import:end gw_test") == 1, rel
        assert "DirectSoundWaveData_vanilla::" in (repo / "sound/direct_sound_data.inc").read_text()
        assert (repo / "sound/voice_groups.inc").read_text().rstrip().endswith("@ gw_import:end gw_test")

        # legacy cleanup
        assert "ghostwood_sound.inc" not in (repo / "data/sound_data.s").read_text()
        assert not (repo / "sound/ghostwood").exists()
        assert not (repo / "sound/direct_sound_samples/ghostwood").exists()

        # BDPCM decode stays close to the source wave
        s = read_sample(Rom(rom_path), 0x2100)
        err = max(abs((b - 256 if b > 127 else b) - x) for b, x in zip(s.pcm, sine))
        print("bdpcm:", s.note, "max error:", err)
        assert err < 20, err

        # cherry-pick + exact .bin mode
        run(["import", str(rom_path), "--voicegroup", "0x100", "--only", "0,4", "--name", "pick", "--repo", str(repo), "--bin"])
        assert list((repo / "sound/direct_sound_samples/gw_pick").glob("*.bin"))
        assert "voice_group gw_pick" in (repo / "sound/voicegroups/gw_pick.inc").read_text()

        assemble_check(repo, rom_bytes, rom_path)
        print("\nselftest OK")


if __name__ == "__main__":
    main()
