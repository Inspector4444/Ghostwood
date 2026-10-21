"""Sample extraction: DirectSound headers, BDPCM decoding, AIFF writing."""
import hashlib
import math
import struct
from dataclasses import dataclass

from rom import RomError


class SampleError(Exception):
    pass


# BDPCM delta table used by the m4a mixer
LUT = (0, 1, 4, 9, 16, 25, 36, 49, -64, -49, -36, -25, -16, -9, -4, -1)
BLOCK_SAMPLES = 64
BLOCK_BYTES = 33


@dataclass
class Sample:
    off: int
    flags: int
    compressed: bool
    loop: bool
    freq: int          # Hz * 1024, as stored in the header
    loop_start: int
    length: int        # samples after decoding
    header: bytes
    raw: bytes         # as stored in ROM (compressed if BDPCM)
    pcm: bytes         # signed 8-bit, decoded
    note: str
    digest: str


def _s8(b):
    return b - 256 if b >= 128 else b


def _decode_blocks(raw, length, hi_first, skip):
    out = bytearray()
    for b in range(0, len(raw) - BLOCK_BYTES + 1, BLOCK_BYTES):
        blk = raw[b:b + BLOCK_BYTES]
        acc = _s8(blk[0])
        out.append(acc & 0xFF)
        for i in range(1, BLOCK_SAMPLES):
            n = i - 1 + skip
            byte = blk[1 + n // 2]
            hi = (n % 2 == 0) == hi_first
            nib = (byte >> 4) if hi else (byte & 0xF)
            acc = ((acc + LUT[nib] + 128) & 0xFF) - 128
            out.append(acc & 0xFF)
    return bytes(out[:length])


def _roughness(pcm):
    total, prev = 0, None
    for b in pcm:
        v = _s8(b)
        if prev is not None:
            total += abs(v - prev)
        prev = v
    return total


def bdpcm_decode(raw, length):
    """Decode BDPCM. The nibble order/offset is not assumed: all four plausible
    layouts are tried and the smoothest result wins (a wrong layout scrambles
    the deltas and is wildly noisier). Returns (pcm, description)."""
    cands = []
    for hi_first in (True, False):
        for skip in (0, 1):
            pcm = _decode_blocks(raw, length, hi_first, skip)
            cands.append((_roughness(pcm), hi_first, skip, pcm))
    cands.sort(key=lambda c: c[0])
    best = cands[0]
    if cands[1][0] <= best[0] * 1.1 + 8:
        # On smooth material the layouts differ by ~1-sample shifts and cannot be
        # told apart from the audio, so fall back to the a-priori layout.
        best = next(c for c in cands if c[1] and c[2] == 0)
        return best[3], "BDPCM nibble layout assumed (hi-first); audibly near-identical, --bin is bit-exact"
    return best[3], f"BDPCM layout inferred ({'hi' if best[1] else 'lo'}-first, skip{best[2]})"


def read_sample(rom, off):
    try:
        hdr = rom.read(off, 16)
    except RomError as e:
        raise SampleError(str(e))
    flags, freq, loop_start, length = struct.unpack("<IIII", hdr)
    if flags & ~0x40000001:
        raise SampleError(f"unknown flags 0x{flags:08X}")
    compressed = bool(flags & 1)
    loop = bool(flags & 0x40000000)
    if length == 0:
        raise SampleError("zero length (synth/Golden Sun style sample)")
    if length > 0x3FFFFF:
        raise SampleError("implausible length")
    if freq == 0:
        raise SampleError("zero pitch")
    nbytes = ((length + BLOCK_SAMPLES - 1) // BLOCK_SAMPLES) * BLOCK_BYTES if compressed else length
    try:
        raw = rom.read(off + 16, nbytes)
    except RomError as e:
        raise SampleError(str(e))
    note = ""
    if compressed:
        pcm, note = bdpcm_decode(raw, length)
    else:
        pcm = raw
    if loop and loop_start >= length:
        note = (note + " loop start out of range, clamped to 0").strip()
        loop_start = 0
    digest = hashlib.sha1(hdr + raw).hexdigest()
    return Sample(off, flags, compressed, loop, freq, loop_start, length, hdr, raw, pcm, note, digest)


def _ext80(x):
    """IEEE 754 80-bit extended, big endian (AIFF sample rate)."""
    if x == 0:
        return b"\0" * 10
    m, e = math.frexp(x)
    return struct.pack(">HQ", e + 16382, int(m * (1 << 64)))


def _pstr(s):
    b = bytes([len(s)]) + s.encode("ascii")
    return b + b"\0" if len(b) % 2 else b


def _chunk(tag, body):
    c = tag + struct.pack(">I", len(body)) + body
    return c + b"\0" if len(body) % 2 else c


def write_aiff(path, s):
    """8-bit mono AIFF in the shape pokeemerald's aif2pcm reads: COMM, MARK + INST
    for the loop, base note 60 so the stored rate maps 1:1 onto the header pitch."""
    rate = s.freq / 1024.0
    comm = struct.pack(">hIh", 1, len(s.pcm), 8) + _ext80(rate)
    chunks = [_chunk(b"COMM", comm)]
    if s.loop:
        mark = struct.pack(">H", 2)
        mark += struct.pack(">hI", 1, s.loop_start) + _pstr("start")
        mark += struct.pack(">hI", 2, len(s.pcm)) + _pstr("end")
        inst = struct.pack(">6bh6h", 60, 0, 0, 127, 0, 127, 0, 1, 1, 2, 0, 0, 0)
        chunks += [_chunk(b"MARK", mark), _chunk(b"INST", inst)]
    else:
        inst = struct.pack(">6bh6h", 60, 0, 0, 127, 0, 127, 0, 0, 0, 0, 0, 0, 0)
        chunks.append(_chunk(b"INST", inst))
    chunks.append(_chunk(b"SSND", struct.pack(">II", 0, 0) + s.pcm))
    body = b"AIFF" + b"".join(chunks)
    with open(path, "wb") as f:
        f.write(b"FORM" + struct.pack(">I", len(body)) + body)


def write_bin(path, s):
    """Exact in-ROM sample: 16-byte header + stored (possibly compressed) data."""
    with open(path, "wb") as f:
        f.write(s.header + s.raw)


def write_wav(path, s):
    """8-bit mono WAV for wav2agb: 'smpl' chunk carries the unity note (60) and loop.
    WAV 8-bit is unsigned, the ROM data is signed, so flip the sign bit."""
    rate = max(1, round(s.freq / 1024.0))
    pcm = bytes(b ^ 0x80 for b in s.pcm)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate, 1, 8)
    loops = 1 if s.loop else 0
    smpl = struct.pack("<9I", 0, 0, round(1e9 / rate), 60, 0, 0, 0, loops, 0)
    if s.loop:
        smpl += struct.pack("<6I", 0, 0, s.loop_start, len(pcm) - 1, 0, 0)

    def ck(tag, body):
        c = tag + struct.pack("<I", len(body)) + body
        return c + b"\0" if len(body) % 2 else c

    body = b"WAVE" + ck(b"fmt ", fmt) + ck(b"smpl", smpl) + ck(b"data", pcm)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(body)) + body)
