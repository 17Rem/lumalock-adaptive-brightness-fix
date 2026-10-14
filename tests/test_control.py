"""Transactions and recovery using synthetic tables; never touches a display."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from lumalock import control as app,profile as p,protocol as b
from fixtures import manifest,ORIGINAL,HIGH


class Fake:
    def __init__(self,initial,fail_write=None,fail_close=False):
        self.memory=bytearray(initial);self.rows=[];self.native_state=0
        self.extended=False;self.writes=0;self.fail_write=fail_write;self.fail_close=fail_close
        self.display=42
        self.target_pin={'backend':'intel','endpoint_id':'intel:test','display_id':42,'edid_sha256':'synthetic','sink':'synthetic'}
    def health(self):return {'0x102':self.native_state}
    def xfer(self,cmd,address,data):
        if cmd!=0 or address!=0x102:raise AssertionError('Unexpected native operation')
        self.native_state=data[0]
    def range_command(self,value):self.extended=bool(value)
    def native(self,address):return self.native_state
    def select_bank(self,page):
        if page!=0:raise AssertionError('Unexpected bank')
    def table(self,packet):return bytes(self.memory)
    def lut_packet(self,data):
        if not self.extended or not p.packet_allowed(data):raise AssertionError('Unexpected LUT packet')
        self.writes+=1
        if self.writes==self.fail_write:raise RuntimeError('injected transfer failure')
        i=int.from_bytes(data[:2],'big')-0x5600;self.memory[i:i+len(data)-2]=data[2:]
    def unload(self):pass


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.patch=patch.object(p,'DATA',manifest()[0]);self.patch.start();self.addCleanup(self.patch.stop)
        p.install_tables(ORIGINAL,HIGH)

    def case(self,action,initial,fail_write=None,fail_close=False,firmware_ok=True):
        fake=Fake(initial,fail_write,fail_close)
        def close(t):
            if t.fail_close:t.fail_close=False;return {'native_restored':False}
            t.extended=False;t.native_state=0
            return {'restricted_window_observed':True,'native_restored':True,'baseline_after':p.BASELINE.hex()}
        def firmware(t,deadline,mark):
            if not firmware_ok:raise RuntimeError('Firmware mismatch')
            mark()
            if firmware_ok=='after_bank':raise RuntimeError('Later firmware mismatch')
            p.install_tables(ORIGINAL,HIGH);return {'profile':'synthetic'}
        with contextlib.ExitStack() as stack:
            folder=Path(stack.enter_context(tempfile.TemporaryDirectory()))
            stack.enter_context(patch.object(app,'STATE_ROOT',folder))
            stack.enter_context(patch.object(app.compatibility,'Transport',return_value=fake))
            stack.enter_context(patch.object(app.compatibility,'verify_firmware',side_effect=firmware))
            stack.enter_context(patch.object(app.compatibility,'expected_block'))
            stack.enter_context(patch.object(b,'restricted',side_effect=lambda t:not t.extended))
            stack.enter_context(patch.object(b,'restore_window',side_effect=close))
            stack.enter_context(patch.object(b,'stable',side_effect=lambda t,address,size,*args:p.BASELINE if address==0xc20 else b'\x0f\xff'))
            stack.enter_context(patch.object(app.subprocess,'Popen',return_value=MagicMock()))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            report=app.run(action)
            states=[json.loads(path.read_text(encoding='utf-8')) for path in folder.glob('*-state.json')]
            self.assertTrue(all(s['done'] for s in states))
        self.assertEqual(fake.native_state,0);self.assertFalse(fake.extended)
        return report,fake

    def test_apply_restore_check_and_idempotence(self):
        for action,initial,expected,count in [('apply',ORIGINAL,HIGH,43),('apply',HIGH,HIGH,0),
                                              ('restore',HIGH,ORIGINAL,43),('check',HIGH,HIGH,0)]:
            with self.subTest(action=action,initial=initial[0]):
                r,t=self.case(action,initial)
                self.assertTrue(r['success']);self.assertEqual(bytes(t.memory),expected);self.assertEqual(t.writes,count)

    def test_write_interruptions_recover(self):
        for n in (1,22,43):
            r,t=self.case('apply',ORIGINAL,fail_write=n)
            self.assertFalse(r['success']);self.assertTrue(r['rollback']['restored']);self.assertEqual(bytes(t.memory),ORIGINAL)

    def test_close_failure_recovers(self):
        r,t=self.case('apply',ORIGINAL,fail_close=True)
        self.assertFalse(r['success']);self.assertTrue(r['rollback']['restored']);self.assertEqual(bytes(t.memory),ORIGINAL)

    def test_unknown_active_curve_not_written(self):
        r,t=self.case('apply',bytes(256))
        self.assertFalse(r['success']);self.assertEqual(t.writes,0)

    def test_firmware_failure_never_writes_lut(self):
        for stage in (False,'after_bank'):
            r,t=self.case('apply',ORIGINAL,firmware_ok=stage)
            self.assertFalse(r['success']);self.assertEqual(t.writes,0);self.assertTrue(r['rollback']['restored'])

    def test_all_44_partial_write_boundaries(self):
        for stop in range(44):
            t=Fake(ORIGINAL);t.extended=True
            for packet in p.packets(HIGH)[:stop]:t.lut_packet(packet)
            for packet in p.packets(ORIGINAL):t.lut_packet(packet)
            self.assertEqual(bytes(t.memory),ORIGINAL)

    def test_noisy_readback_and_persistent_corruption(self):
        bad=bytes([HIGH[0]^0x80])+HIGH[1:];counts={16:0,8:0}
        def noisy(packet):
            counts[packet]+=1
            return bad if packet==8 and counts[8] in (3,6,9) else HIGH
        t=Fake(HIGH)
        with patch.object(t,'table',side_effect=noisy):self.assertTrue(b.verified_table(t,HIGH))
        self.assertEqual(counts,{16:3,8:12})
        with patch.object(t,'table',return_value=bad):
            with self.assertRaises(RuntimeError):b.verified_table(t,HIGH)

    def test_recovery_pin_and_state_curve_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'guard.json';t=Fake(HIGH)
            state={'done':False,'deadline':0,'target_pin':t.target_pin,'bank_started':True,
                   'range_opened':True,'lut_write_started':True,'original_lut':ORIGINAL.hex(),'high_lut':HIGH.hex()}
            path.write_text(json.dumps(state))
            with patch.object(app.compatibility,'Transport',return_value=t) as transport,patch.object(app,'recover',return_value={'restored':True}) as recover:
                app.guard(path);transport.assert_called_once_with(pin=t.target_pin);recover.assert_called_once_with(t,state)
            with patch.object(app.compatibility,'Transport',side_effect=RuntimeError('Target changed')),patch.object(app,'recover') as recover:
                app.guard(path);recover.assert_not_called()
            state['original_lut']=bytes(256).hex();path.write_text(json.dumps(state))
            with patch.object(app.compatibility,'Transport') as transport:
                app.guard(path);transport.assert_not_called()


if __name__=='__main__':unittest.main()
