"""Synthetic test data only; no captured device data or vendor firmware."""
import copy
from lumalock import profile

ORIGINAL=bytes(range(256))
HIGH=bytes([255])*128+ORIGINAL[128:]


def manifest():
    data=copy.deepcopy(profile.DATA)
    data['original_lut_sha256']=profile.digest(ORIGINAL)
    data['high_lut_sha256']=profile.digest(HIGH)
    rom=bytearray((i*17+i//256)%256 for i in range(0x2a000))
    rom[0x29e00:0x29f00]=HIGH;rom[0x29f00:0x2a000]=ORIGINAL
    data['code_sha256']=profile.digest(rom[:0x8000])
    for key in data['blocks']:
        address=int(key,16);value=rom[address:address+256]
        data['blocks'][key]={'full':profile.digest(value),'first':profile.digest(value[:128]),'second':profile.digest(value[128:])}
    return data,bytes(rom)


def edid():
    data=bytearray(128);data[:8]=bytes.fromhex('00ffffffffffff00')
    data[8:12]=bytes.fromhex(profile.DATA['edid_product'])
    data[54:59]=bytes.fromhex('000000fc00')
    data[59:72]=b'NE180QDM-NZ4\n'
    data[127]=(-sum(data[:127]))&255
    return bytes(data)
