"""Voice (instrument) records of an m4a voicegroup.

12 bytes each: type, key, length, pan_sweep, word1, word2.
  direct sound : word1 = sample ptr,        word2 = ADSR bytes
  square 1/2   : word1 = duty (0-3),        word2 = ADSR bytes
  wave (ch 3)  : word1 = ptr to 16 bytes,   word2 = ADSR bytes
  noise        : word1 = period (0/1),      word2 = ADSR bytes
  keysplit 0x40: word1 = sub voicegroup,    word2 = ptr to 128-byte key->index table
  rhythm   0x80: word1 = sub voicegroup (indexed by key)
"""
import struct
from collections import namedtuple

from rom import RomError

Voice = namedtuple("Voice", "type key length pan_sweep w1 w2")
VOICE_SIZE = 12


def read_voice(rom, off):
    try:
        return Voice(*struct.unpack("<BBBBII", rom.read(off, VOICE_SIZE)))
    except RomError:
        return None


def adsr(v):
    w = v.w2
    return (w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF, (w >> 24) & 0xFF)


def is_empty(v):
    return v == Voice(0, 0, 0, 0, 0, 0)


def is_unused_marker(v):
    # Nintendo's filler voice: square 1, key 60, duty 2, ADSR 0,0,15,0
    return (v.type, v.key, v.length, v.pan_sweep, v.w1, v.w2) == (0x01, 0x3C, 0, 0, 2, 0x0F0000)


def classify(v):
    if v.type == 0x40:
        return "keysplit"
    if v.type == 0x80:
        return "rhythm"
    if v.type & 0xC0:
        return "invalid"
    return {0: "direct", 1: "square1", 2: "square2", 3: "wave", 4: "noise"}.get(v.type & 7, "invalid")
