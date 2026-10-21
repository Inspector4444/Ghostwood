"""Turns voices read from a source ROM into pokeemerald-native files.

Everything an import creates carries its name (gw_*) so it is easy to find:

  sound/voicegroups/<name>.inc                       top voicegroup  (voice_group + voice_* macros)
  sound/voicegroups/keysplits/<name>_<addr>.inc      keysplit sub-groups
  sound/voicegroups/drumsets/<name>_<addr>.inc       rhythm (keysplit_all) sub-groups
  sound/direct_sound_samples/<name>/*.wav            samples (the Makefile builds the .bin)
  sound/programmable_wave_samples/<name>_<hash>.pcm  new programmable waves (16 bytes)

plus one delimited block in each of sound/voice_groups.inc, direct_sound_data.inc,
programmable_wave_data.inc and keysplit_tables.inc, so re-importing replaces exactly
what the previous run added and nothing else.
"""
import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

from rom import Rom
from voices import read_voice, adsr, is_empty, is_unused_marker, classify
from samples import read_sample, SampleError, write_aiff, write_bin, write_wav

FILLER = "voice_square_1 60, 0, 0, 2, 0, 0, 15, 0"   # Nintendo's unused-slot voice
DUTY = {0: "12.5%", 1: "25%", 2: "50%", 3: "75%"}
NATIVE = {
    ("direct", 0x00): "voice_directsound",
    ("direct", 0x08): "voice_directsound_no_resample",
    ("square1", 0x01): "voice_square_1",
    ("square1", 0x09): "voice_square_1_alt",
    ("square2", 0x02): "voice_square_2",
    ("square2", 0x0A): "voice_square_2_alt",
    ("wave", 0x03): "voice_programmable_wave",
    ("wave", 0x0B): "voice_programmable_wave_alt",
    ("noise", 0x04): "voice_noise",
    ("noise", 0x0C): "voice_noise_alt",
}
GROUP_DIR = {"keysplit": "keysplits", "drumset": "drumsets"}
BEGIN = "@ gw_import:begin {}"
END = "@ gw_import:end {}"
LEGACY_INCLUDE = '.include "sound/ghostwood/ghostwood_sound.inc"'


def parse_keysplit(t):
    """128 raw bytes read from a key-table pointer -> (lo, [(index, last_key), ...]) or None.

    mks4agb tables only cover a key range lo..hi, and the pointer sits `lo` bytes *before*
    the real data, so the bytes before and after that range belong to neighbouring tables
    (the repo's keysplit_tables.inc explains this). The real range is the run where the
    index steps by 0 or +1; the run that climbs the most wins."""
    best, k = None, 0
    while k < 128:
        if t[k] >= 0x80:
            k += 1
            continue
        e = k
        while e + 1 < 128 and t[e + 1] < 0x80 and 0 <= t[e + 1] - t[e] <= 1:
            e += 1
        score = (t[e] - t[k], e - k)
        if best is None or score > best[0]:
            best = (score, k, e)
        k = e + 1
    if best is None:
        return None
    _, lo, hi = best
    splits = []
    for key in range(lo, hi + 1):
        if splits and splits[-1][0] == t[key]:
            splits[-1][1] = key
        else:
            splits.append([t[key], key])
    return lo, [(v, e) for v, e in splits]


class Importer:
    def __init__(self, rom, name, fmt="wav", vanilla_waves=None):
        self.rom = rom
        self.name = name
        self.fmt = fmt                      # wav (wav2agb), aif (aif2pcm) or bin (exact copy)
        self.vanilla_waves = vanilla_waves or {}
        self.reused_waves = set()
        self._samples = {}                  # pointer word -> Sample | None
        self._sample_err = {}
        self._by_digest = {}                # digest -> (label, stem, Sample)
        self.waves = {}                     # 16 bytes -> new label
        self.tables = {}                    # table offset -> parsed (lo, splits)
        self._ks = {}
        self.need = {}                      # (kind, group offset) -> set of used indexes
        self.warnings = []
        self.out = None

    # ---- lookups -------------------------------------------------------
    def sample(self, word):
        if word in self._samples:
            return self._samples[word]
        s = None
        if not self.rom.ptr_ok(word, 16):
            self._sample_err[word] = "pointer outside ROM"
        else:
            try:
                s = read_sample(self.rom, Rom.to_off(word))
            except SampleError as e:
                self._sample_err[word] = str(e)
        self._samples[word] = s
        return s

    def sample_label(self, word):
        s = self.sample(word)
        hit = self._by_digest.get(s.digest)
        if hit is None:
            stem = f"{self.name}_{s.off:06x}"
            hit = (f"DirectSoundWaveData_{stem}", stem, s)
            self._by_digest[s.digest] = hit
        return hit[0]

    def wave_label(self, word):
        data = self.rom.read(Rom.to_off(word), 16)
        if data in self.vanilla_waves:          # identical wave already in the repo
            self.reused_waves.add(self.vanilla_waves[data])
            return self.vanilla_waves[data]
        if data not in self.waves:
            h = hashlib.sha1(data).hexdigest()[:8]
            self.waves[data] = f"ProgrammableWaveData_{self.name}_{h}"
        return self.waves[data]

    def keysplit(self, word):
        off = Rom.to_off(word)
        if off not in self._ks:
            self._ks[off] = parse_keysplit(self.rom.read(off, 128))
        return self._ks[off]

    def table_label(self, word):
        off = Rom.to_off(word)
        self.tables[off] = self.keysplit(word)
        return f"keysplit_{self.name}_{off:06x}"

    def group_name(self, kind, off):
        return f"{self.name}_{kind}_{off:06x}"

    def group_path(self, kind, off):
        return f"sound/voicegroups/{GROUP_DIR[kind]}/{self.name}_{off:06x}.inc"

    # ---- classification ------------------------------------------------
    def resolve(self, v, is_sub):
        """(kind, reason). kind: a voice kind, 'empty', 'unused' or 'invalid'."""
        if v is None or is_empty(v):
            return "empty", ""
        if is_unused_marker(v):
            return "unused", ""
        kind = classify(v)
        r = self.rom
        if kind == "invalid":
            return kind, f"unknown voice type 0x{v.type:02x}"
        if kind in ("keysplit", "rhythm"):
            if is_sub:
                return "invalid", "nested split/rhythm voice"
            if not r.ptr_ok(v.w1, 12):
                return "invalid", "bad sub-voicegroup pointer"
            if kind == "keysplit":
                if not r.ptr_ok(v.w2, 128):
                    return "invalid", "bad key table pointer"
                if self.keysplit(v.w2) is None:
                    return "invalid", "unreadable key table"
        elif kind == "direct":
            if self.sample(v.w1) is None:
                return "invalid", "sample: " + self._sample_err.get(v.w1, "unreadable")
        elif kind in ("square1", "square2"):
            if v.w1 > 3:
                return "invalid", f"duty {v.w1} out of range"
        elif kind == "wave":
            if not r.ptr_ok(v.w1, 16):
                return "invalid", "wave pointer outside ROM"
        elif kind == "noise":
            if v.w1 not in (0, 1, 0x1000000):
                return "invalid", f"noise period {v.w1:#x}"
        return kind, ""

    def split_indices(self, v):
        _, splits = self.keysplit(v.w2)
        return list(range(splits[0][0], splits[-1][0] + 1))

    def describe(self, v, is_sub=False):
        kind, why = self.resolve(v, is_sub)
        if kind in ("empty", "unused"):
            return kind, ""
        if kind == "invalid":
            return kind, why
        flags = "".join(n for bit, n in ((0x08, " fixed"), (0x10, " rev")) if v.type & bit and kind != "keysplit")
        if kind == "direct":
            s = self.sample(v.w1)
            d = f"@0x{s.off:06x} {s.freq / 1024:.0f}Hz len={s.length}"
            if s.loop:
                d += f" loop@{s.loop_start}"
            if s.compressed:
                d += " BDPCM"
            return kind, d + flags
        if kind in ("square1", "square2"):
            d = f"duty {DUTY[v.w1]}"
            if kind == "square1" and v.pan_sweep and not v.pan_sweep & 0x80:
                d += f" sweep=0x{v.pan_sweep:02x}"
            return kind, d + flags
        if kind == "wave":
            return kind, "wave " + self.rom.read(Rom.to_off(v.w1), 16).hex() + flags
        if kind == "noise":
            return kind, ("short(7-bit) " if v.w1 else "long(15-bit) ") + "LFSR" + flags
        if kind == "keysplit":
            idx = self.split_indices(v)
            lo, splits = self.keysplit(v.w2)
            return kind, (f"group@0x{Rom.to_off(v.w1):06x} voices {idx[0]}-{idx[-1]}, "
                          f"keys {lo}-{splits[-1][1]}")
        return kind, f"group@0x{Rom.to_off(v.w1):06x}"

    # ---- one voice -> macro line(s) -------------------------------------
    def voice_text(self, v, is_sub):
        """Returns ([lines], comment). Uses the repo's voice_* macros whenever the
        voice is expressible with them, raw .byte/.4byte lines otherwise."""
        kind, why = self.resolve(v, is_sub)
        if kind in ("empty", "unused"):
            return [FILLER], ""
        if kind == "invalid":
            if not is_sub:
                self.warnings.append(why)
            return [FILLER], "dropped: " + why
        _, detail = self.describe(v, is_sub)
        comment = f"{kind} {detail}".strip()
        ps = v.pan_sweep
        exact = v.length == 0                      # macros always write length 0
        a, d, s, r = adsr(v)
        adsr_s = f"{a}, {d}, {s}, {r}"
        head = f".byte 0x{v.type:02x}, {v.key}, {v.length}, 0x{ps:02x}"

        if kind in ("keysplit", "rhythm"):
            gk = "keysplit" if kind == "keysplit" else "drumset"
            off = Rom.to_off(v.w1)
            self.need.setdefault((gk, off), set()).update(
                self.split_indices(v) if kind == "keysplit" else ())
            gsym = "voicegroup_" + self.group_name(gk, off)
            exact = exact and v.key == 0 and ps == 0
            if kind == "keysplit":
                tsym = self.table_label(v.w2)
                macro, args, tail = "voice_keysplit", f"{gsym}, {tsym}", [f".4byte {gsym}", f".4byte {tsym}"]
            else:
                exact = exact and v.w2 == 0
                macro, args, tail = "voice_keysplit_all", gsym, [f".4byte {gsym}", f".4byte {v.w2}"]
        else:
            if ps & 0x80:
                pan, sweep = ps & 0x7F, 0
                exact = exact and pan != 0         # a bare 0x80 cannot be written with the macros
            else:
                pan, sweep = 0, ps
                exact = exact and (kind == "square1" or sweep == 0)
            macro = NATIVE.get((kind, v.type))
            exact = exact and macro is not None
            if kind == "direct":
                w1 = self.sample_label(v.w1)
                args = f"{v.key}, {pan}, {w1}, {adsr_s}"
            elif kind == "wave":
                w1 = self.wave_label(v.w1)
                args = f"{v.key}, {pan}, {w1}, {adsr_s}"
            elif kind == "square1":
                w1 = str(v.w1)
                args = f"{v.key}, {pan}, {sweep}, {w1}, {adsr_s}"
            else:                                   # square2, noise
                w1 = str(v.w1)
                args = f"{v.key}, {pan}, {w1}, {adsr_s}"
            tail = [f".4byte {w1}", f".byte {adsr_s}"]

        if exact:
            return [f"{macro} {args}"], comment
        return [head] + tail, comment + " (raw bytes: not expressible with the voice_* macros)"

    @staticmethod
    def _fmt_group(gname, rows):
        out = [f"voice_group {gname}"]
        for i, lines, c in rows:
            first = "    " + lines[0]
            if c:
                first += f"    @ {i} {c}"
            out.append(first)
            out += ["    " + l for l in lines[1:]]
        return "\n".join(out) + "\n"

    # ---- whole import ---------------------------------------------------
    def build(self, slots):
        files = {}
        rows = [(i, *self.voice_text(v, False)) for i, v in enumerate(slots)]
        top = f"sound/voicegroups/{self.name}.inc"
        files[top] = self._fmt_group(self.name, rows)

        includes = []
        for (kind, off), used in sorted(self.need.items()):
            n = 128 if kind == "drumset" else max(used) + 1
            sub = []
            for j in range(n):
                # keysplit: only indexes the key table can reach are real voices; the rest is
                # whatever bytes follow the group in the source ROM, so it becomes filler
                v = read_voice(self.rom, off + 12 * j) if (kind == "drumset" or j in used) else None
                sub.append((j, *self.voice_text(v, True)))
            path = self.group_path(kind, off)
            files[path] = self._fmt_group(self.group_name(kind, off), sub)
            includes.append(path)
        includes.append(top)

        ds = []
        for label, stem, _ in sorted(self._by_digest.values(), key=lambda t: t[0]):
            ds += ["\t.align 2", f"{label}::",
                   f'\t.incbin "sound/direct_sound_samples/{self.name}/{stem}.bin"']
        pw, blobs = [], {}
        for data, label in sorted(self.waves.items(), key=lambda kv: kv[1]):
            path = f"sound/programmable_wave_samples/{label[len('ProgrammableWaveData_'):]}.pcm"
            blobs[path] = data
            pw += ["\t.align 2", f"{label}::", f'\t.incbin "{path}"']
        ks = []
        for off in sorted(self.tables):
            lo, splits = self.tables[off]
            ks.append(f"keysplit {self.name}_{off:06x}, {lo}")
            ks += [f"split {v}, {e}" for v, e in splits]

        self.out = SimpleNamespace(
            files=files, blobs=blobs,
            blocks={
                "sound/direct_sound_data.inc": "\n".join(ds),
                "sound/programmable_wave_data.inc": "\n".join(pw),
                "sound/keysplit_tables.inc": "\n".join(ks),
                "sound/voice_groups.inc": "\n".join(f'.include "{p}"' for p in includes),
            })
        return self.out

    def write_assets(self, root):
        root = Path(root)
        d = root / "sound/direct_sound_samples" / self.name
        notes = []
        if self._by_digest:
            d.mkdir(parents=True, exist_ok=True)
        for _, stem, s in self._by_digest.values():
            if self.fmt == "bin":
                write_bin(d / f"{stem}.bin", s)
            elif self.fmt == "aif":
                write_aiff(d / f"{stem}.aif", s)
            else:
                write_wav(d / f"{stem}.wav", s)
            if s.note:
                notes.append(f"{stem}: {s.note}")
        for rel, data in self.out.blobs.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return notes


# ---- repo-level helpers ------------------------------------------------
def _block_re(name):
    return re.compile(r"\n*" + re.escape(BEGIN.format(name)) + r"\n.*?" + re.escape(END.format(name)) + r"\n", re.S)


def put_block(path, name, body):
    """Replaces (or appends) this import's delimited block. An empty body removes it."""
    path = Path(path)
    text = path.read_text() if path.exists() else ""
    block = f"\n{BEGIN.format(name)}\n{body.rstrip()}\n{END.format(name)}\n" if body.strip() else ""
    rx = _block_re(name)
    if rx.search(text):
        text = rx.sub(lambda m: block, text, count=1)
    elif block:
        text = text.rstrip("\n") + "\n" + block
    else:
        return
    path.write_text(text)


def vanilla_waves(repo):
    """16-byte waves already registered in the repo (outside any gw_import block) -> label."""
    p = Path(repo) / "sound/programmable_wave_data.inc"
    if not p.exists():
        return {}
    text = re.sub(r"@ gw_import:begin (\S+)\n.*?@ gw_import:end \1\n", "", p.read_text(), flags=re.S)
    out = {}
    for m in re.finditer(r'^(\w+)::\s*\n\s*\.incbin\s+"([^"]+)"', text, re.M):
        f = Path(repo) / m.group(2)
        if f.is_file() and f.stat().st_size == 16:
            out.setdefault(f.read_bytes(), m.group(1))
    return out


def migrate_legacy(repo, name):
    """Cleans up after the first version of this tool (raw macros under sound/ghostwood/).
    Only touches what that version generated. Returns a list of log lines."""
    repo = Path(repo)
    log = []
    cands = [*repo.glob("*.s"), *(repo / "data").glob("*.s"), *(repo / "data").glob("*.inc"),
             *(repo / "sound").glob("*.s"), *(repo / "sound").glob("*.inc")]
    for p in cands:
        try:
            t = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if LEGACY_INCLUDE in t:
            p.write_text(re.sub(r"\n?[ \t]*" + re.escape(LEGACY_INCLUDE) + r"[ \t]*(?=\n|$)", "", t))
            log.append(f"removed old include line from {p.relative_to(repo)}")
    leg = repo / "sound/ghostwood"
    for f in (leg / "imports" / f"{name}.inc", leg / "imports" / f"{name}.report.txt"):
        if f.exists():
            f.unlink()
            log.append(f"deleted {f.relative_to(repo)}")
    if leg.is_dir() and not list((leg / "imports").glob("*.inc")):
        for f in (leg / "ghostwood_sound.inc", leg / "gw_voice_macros.inc"):
            if f.exists():
                f.unlink()
                log.append(f"deleted {f.relative_to(repo)}")
        for d in (leg / "imports", leg):
            try:
                d.rmdir()
            except OSError:
                pass
    sd = repo / "sound/direct_sound_samples/ghostwood" / name
    if sd.is_dir():
        pat = re.compile(rf"{re.escape(name)}_[0-9a-f]{{6}}\.(wav|aif|bin)")
        n = 0
        for f in sd.iterdir():
            if pat.fullmatch(f.name):
                f.unlink()
                n += 1
        log.append(f"deleted {n} old sample files in {sd.relative_to(repo)}")
        for d in (sd, sd.parent):
            try:
                d.rmdir()
            except OSError:
                pass
    return log
