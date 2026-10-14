"""Non-reversible compatibility fingerprints; curves are read from the device."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
PATH=Path(__file__).resolve().parent/'profiles/ne180qdm_nz4.json'
MANIFEST_SHA256='e46887685b15592236c8100188de64a185b7aca1222e933bc10bcfc942dd37f6'
raw=PATH.read_bytes()
if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA256:
    raise RuntimeError('Compatibility profile is damaged')
DATA=json.loads(raw)
BASELINE=bytes.fromhex('00001000')
ORIGINAL=None
TARGET=None
CHUNKS=tuple((i,min(6,256-i)) for i in range(0,256,6))


def digest(data):return hashlib.sha256(data).hexdigest()


def install_tables(original,high):
    global ORIGINAL,TARGET
    if len(original)!=256 or digest(original)!=DATA['original_lut_sha256']:
        raise RuntimeError('Original factory LUT fingerprint mismatch')
    if len(high)!=256 or digest(high)!=DATA['high_lut_sha256']:
        raise RuntimeError('High factory LUT fingerprint mismatch')
    ORIGINAL=bytes(original);TARGET=bytes(high)


def packets(data):
    if data is None or len(data)!=256:raise RuntimeError('Verified factory curves are not loaded')
    return [(0x5600+i).to_bytes(2,'big')+data[i:i+n] for i,n in CHUNKS]


def packet_allowed(data):
    return ORIGINAL is not None and TARGET is not None and data in packets(ORIGINAL)+packets(TARGET)
