"""Minimal SF2 preset reader — no dependencies, works on Python 3.13+."""
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Preset:
    bank: int
    number: int
    name: str


def read_presets(path: str | Path) -> List[Preset]:
    """Return all presets from an SF2 file sorted by bank then preset number."""
    presets: List[Preset] = []

    with open(path, 'rb') as f:
        if f.read(4) != b'RIFF':
            raise ValueError('Not a RIFF file')
        riff_size = struct.unpack('<I', f.read(4))[0]
        if f.read(4) != b'sfbk':
            raise ValueError('Not an SF2 soundfont file')

        end = 8 + riff_size
        while f.tell() < end - 8:
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break
            chunk_size = struct.unpack('<I', f.read(4))[0]

            if chunk_id == b'LIST':
                list_type = f.read(4)
                if list_type == b'pdta':
                    _parse_pdta(f, chunk_size - 4, presets)
                    break
                else:
                    # Skip to end of this LIST chunk
                    f.seek(chunk_size - 4, 1)
            else:
                # Chunks are word-aligned
                f.seek(chunk_size + (chunk_size % 2), 1)

    presets.sort(key=lambda p: (p.bank, p.number))
    return presets


def _parse_pdta(f, size: int, presets: List[Preset]) -> None:
    end = f.tell() + size
    while f.tell() < end - 8:
        sub_id = f.read(4)
        if len(sub_id) < 4:
            break
        sub_size = struct.unpack('<I', f.read(4))[0]

        if sub_id == b'phdr':
            # Each PHDR record is 38 bytes
            for _ in range(sub_size // 38):
                data = f.read(38)
                name_bytes = data[:20]
                # Null-terminate at the first \x00 (SF2 names are C strings)
                null = name_bytes.find(b'\x00')
                if null != -1:
                    name_bytes = name_bytes[:null]
                name = name_bytes.decode('ascii', errors='replace').strip()
                preset_num = struct.unpack('<H', data[20:22])[0]
                bank_num = struct.unpack('<H', data[22:24])[0]
                # 'EOP' is the end-of-presets sentinel record
                if name and name != 'EOP':
                    presets.append(Preset(bank=bank_num, number=preset_num, name=name))
        else:
            f.seek(sub_size + (sub_size % 2), 1)
