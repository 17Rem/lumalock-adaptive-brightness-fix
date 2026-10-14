"""Discovery/profile regression tests; all NVAPI and device reads are simulated."""
import hashlib,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
from lumalock import compatibility as d,profile
from fixtures import manifest,edid,ORIGINAL,HIGH

EDID=edid()
def row(number,edid=EDID):
    return {'display_id':number,'display':hex(number),'candidate':True,'edid':edid.hex(),
            'backend':'nvidia','endpoint_id':f'nvidia:0x{number:08X}',
            'edid_sha256':hashlib.sha256(edid).hexdigest(),'sink':d.b.EXPECTED_SINK.hex()}

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        data,self.rom=manifest()
        self.profile_patch=patch.object(profile,'DATA',data);self.profile_patch.start()
        self.addCleanup(self.profile_patch.stop)

    def test_different_display_number(self):self.assertEqual(d.choose([row(42)])['display_id'],42)
    def test_ambiguous_requires_selection(self):
        with self.assertRaisesRegex(RuntimeError,'Multiple'):d.choose([row(42),row(43)])
        self.assertEqual(d.choose([row(42),row(43)],43)['display_id'],43)
    def test_recovery_never_chooses_another_matching_screen(self):
        with self.assertRaisesRegex(RuntimeError,'Recovery target'):d.choose([row(43)],pin=row(42))
    def test_replaced_edid_rejected(self):
        other=row(42);other['edid_sha256']='different'
        with self.assertRaises(RuntimeError):d.choose([other],pin=row(42))
    def test_missing_or_unsupported_requested(self):
        for rows,requested in (([],None),([row(42)],44),([{'display_id':42,'candidate':False}],42)):
            with self.assertRaises(RuntimeError):d.choose(rows,requested)
    def test_serial_and_date_variation(self):
        other=bytearray(EDID);other[12:18]=bytes.fromhex('123456780123');other[127]=(-sum(other[:127]))&255
        self.assertTrue(d.edid_matches(other))
    def test_corrupt_or_wrong_panel(self):
        for index in (0,8,10,60,127):
            other=bytearray(EDID);other[index]^=1
            if index!=127:other[127]=(-sum(other[:127]))&255
            self.assertFalse(d.edid_matches(other))
    def test_inventory_skips_other_displays_without_writes(self):
        class Fake:
            backend='intel';semantics='raw-aux-mot'
            def __init__(self,n):self.number=n;self.key=f'intel:{n}'
            def exchange(self,cmd,address,data,n):
                assert cmd==1 and not data
                return d.b.EXPECTED_SINK[address-0x400:address-0x400+1] if self.number==42 else bytes(1)
        pool=SimpleNamespace(endpoints=[Fake(41),Fake(42)])
        with patch.object(d,'read_edid',return_value=EDID):rows=d.inventory(pool)
        self.assertFalse(rows[0]['candidate']);self.assertTrue(rows[1]['candidate'])
    def test_backend_identity_is_part_of_recovery_pin(self):
        other=row(42);other.update(backend='intel',endpoint_id='intel:42')
        with self.assertRaises(RuntimeError):d.choose([other],pin=row(42))
        self.assertEqual(d.choose([row(42),other],requested='intel:42'),other)
    def test_old_pin_without_backend_rejected(self):
        pin=row(42);del pin['backend']
        with self.assertRaises(RuntimeError):d.choose([row(42)],pin=pin)
    def test_firmware_and_both_factory_tables(self):
        rom=self.rom
        class Flash:
            page=0
            def select_bank(self,page):self.page=page
            def read_burst(self,device,offset,size,settle):
                address=self.page*4096+offset-0xd000
                return rom[address:address+size]
        t=Flash();report=d.verify_firmware(t,time.time()+20)
        self.assertEqual(t.page,0);self.assertEqual(report['code_bytes'],32768)
        self.assertTrue(report['factory_tables_verified'])
    def test_wrong_firmware_never_extends_window_or_writes_lut(self):
        class Bad:
            def read_burst(self,*args):return bytes(256)
        with self.assertRaisesRegex(RuntimeError,'Firmware profile mismatch'):
            d.verify_firmware(Bad(),time.time()+20)
    def test_mismatched_original_factory_table_rejected(self):
        rom=self.rom
        class Flash:
            page=0
            def select_bank(self,page):self.page=page
            def read_burst(self,device,offset,size,settle):
                address=self.page*4096+offset-0xd000
                data=bytearray(rom[address:address+size])
                if address==0x29f00:data[0]^=1
                return bytes(data)
        with self.assertRaisesRegex(RuntimeError,'Firmware profile mismatch'):
            d.verify_firmware(Flash(),time.time()+20)
    def test_deadline(self):
        with self.assertRaisesRegex(RuntimeError,'deadline'):d.expected_block(None,0xd000,256,profile.digest(bytes(256)),time.time()-1)

if __name__=='__main__':unittest.main()
