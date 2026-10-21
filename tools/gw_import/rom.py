"""ROM access and m4a (Sappy / MP2K) song table discovery.

The detection pattern and the +40 song-table field offset are ported from
gba_mus_ripper's sappy_detector.c.
"""
import struct
from pathlib import Path

# Start of m4a SelectSong(); a pointer to the song table sits 40 bytes in.
SELECTSONG = bytes([
    0x00, 0xB5, 0x00, 0x04, 0x07, 0x4A, 0x08, 0x49,
    0x40, 0x0B, 0x40, 0x18, 0x83, 0x88, 0x59, 0x00,
    0xC9, 0x18, 0x89, 0x00, 0x89, 0x18, 0x0A, 0x68,
    0x01, 0x68, 0x10, 0x1C, 0x00, 0xF0,
])
SONGTABLE_FIELD = 40


class RomError(Exception):
    pass


def parse_addr(text):
    """Accepts a ROM offset (0x1234) or a GBA address (0x08001234)."""
    v = int(str(text), 0)
    return v & 0x1FFFFFF if v >= 0x08000000 else v


class Rom:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.size = len(self.data)

    def read(self, off, n):
        if off < 0 or n < 0 or off + n > self.size:
            raise RomError(f"read of {n} bytes at 0x{off:X} is outside the ROM")
        return self.data[off:off + n]

    def u32(self, off):
        return struct.unpack("<I", self.read(off, 4))[0]

    @staticmethod
    def is_rom_ptr(v):
        return (v >> 24) in (0x08, 0x09)

    def ptr_ok(self, v, span=1):
        return self.is_rom_ptr(v) and (v & 0x1FFFFFF) + span <= self.size

    @staticmethod
    def to_off(v):
        return v & 0x1FFFFFF


def find_song_table(rom):
    """Returns the ROM offset of the song table, or None."""
    start = 0
    while True:
        at = rom.data.find(SELECTSONG, start)
        if at < 0:
            return None
        start = at + 1
        if at + SONGTABLE_FIELD + 4 > rom.size:
            continue
        v = rom.u32(at + SONGTABLE_FIELD)
        if not rom.ptr_ok(v, 8):
            continue
        table = Rom.to_off(v)
        # first non-null entry must be a valid song pointer
        for i in range(64):
            if table + i * 8 + 4 > rom.size:
                break
            p = rom.u32(table + i * 8)
            if p == 0:
                continue
            if rom.ptr_ok(p, 4):
                return table
            break


def list_song_banks(rom, table_off):
    """Yields (song_index, song_offset, voicegroup_offset_or_None)."""
    off = table_off
    # some games (Fire Emblem) start the table with null entries
    while off < table_off + 4 * 64 and rom.u32(off) == 0:
        off += 4
    out = []
    idx = 0
    while off + 8 <= rom.size:
        p = rom.u32(off)
        if not rom.ptr_ok(p, 8):
            break
        song = Rom.to_off(p)
        vg = rom.u32(song + 4)
        out.append((idx, song, Rom.to_off(vg) if rom.ptr_ok(vg, 12) else None))
        idx += 1
        off += 8
    return out
