"""Fail if the output is not an ELF x86_64 type-2 AppImage."""
from pathlib import Path
import struct
import sys

p = Path(sys.argv[1])
with p.open('rb') as f:
    header = f.read(64)
assert header[:4] == b'\x7fELF', 'Not ELF'
assert header[4:6] == b'\x02\x01', 'Not little-endian 64-bit ELF'
assert header[8:11] == b'AI\x02', 'Not a type-2 AppImage'
assert struct.unpack_from('<H', header, 18)[0] == 62, 'Not x86_64'
assert p.stat().st_size > 10_000_000, 'Unexpectedly small bundle'
print('Verified x86_64 type-2 AppImage:', p)
