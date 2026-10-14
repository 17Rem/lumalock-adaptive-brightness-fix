"""Offline driver-contract tests; no driver initialization or hardware access."""
import ctypes as c
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch,Mock
from lumalock import profile
from lumalock import backends as a
from lumalock.protocol import ProtocolTransport
from lumalock.vendor.gpu_aux.intel import _CtlAuxAccessArgs
from lumalock.vendor.gpu_aux.adl import _NativeAuxRequest


def port(handle=123,physical=45):
    return NS(adapter=NS(bus=1,device=2,function=0,index=9),
              logical_display_index=handle,physical_display_index=physical)


from fixtures import manifest,ORIGINAL,HIGH

class DriverTests(unittest.TestCase):
    def setUp(self):
        self.profile_patch=patch.object(profile,'DATA',manifest()[0]);self.profile_patch.start()
        self.addCleanup(self.profile_patch.stop)
        profile.install_tables(ORIGINAL,HIGH)

    def test_nvidia_length_encoding_and_mot(self):
        calls=[]
        def transfer(display,pointer,size):
            r=c.cast(pointer,c.POINTER(a.b.Request)).contents
            calls.append((display,r.command,r.address,r.length,bytes(r.data[:r.length+1])))
            r.reply=0;r.data[:2]=b'OK';return 0
        e=a.NvidiaEndpoint(NS(aux=transfer),42)
        self.assertEqual(e.exchange(6,0xc4,b'',2),b'OK')
        e.exchange(5,0xc4,b'\x56\x00',2)
        self.assertEqual(calls[0][:4],(42,6,0xc4,1))
        self.assertEqual(calls[1],(42,5,0xc4,1,b'\x56\x00'))

    def test_intel_exact_phase_flags_and_payloads(self):
        calls=[]
        def transfer(handle,pointer):
            r=c.cast(pointer,c.POINTER(_CtlAuxAccessArgs)).contents
            calls.append((handle.value,r.OpType,r.Flags,r.Address,r.DataSize,bytes(r.Data[:r.DataSize])))
            if r.OpType==1:r.Data[:r.DataSize]=b'R'*r.DataSize
            return 0
        e=a.DriverEndpoint('intel',NS(_ctl=NS(ctlAUXAccess=transfer)),port())
        for cmd,op,flags in ((0,2,1),(1,1,1),(2,2,2),(3,1,2),(5,2,4),(6,1,4)):
            payload=b'W' if op==2 else b''
            self.assertEqual(e.exchange(cmd,0xc4,payload,1),payload if op==2 else b'R')
            self.assertEqual(calls[-1][:5],(123,op,flags,0xc4,1))
        self.assertEqual(e.key,a.DriverEndpoint('intel',None,port(handle=999)).key)

    def test_intel_failed_write_not_retried(self):
        transfer=Mock(return_value=1)
        e=a.DriverEndpoint('intel',NS(_ctl=NS(ctlAUXAccess=transfer)),port())
        with self.assertRaises(RuntimeError):e.exchange(2,0xc4,b'\xff\x10\x01',3)
        self.assertEqual(transfer.call_count,1)

    def test_intel_short_read_rejected(self):
        def short(handle,pointer):
            c.cast(pointer,c.POINTER(_CtlAuxAccessArgs)).contents.DataSize=0;return 0
        e=a.DriverEndpoint('intel',NS(_ctl=NS(ctlAUXAccess=short)),port())
        with self.assertRaisesRegex(RuntimeError,'short'):e.exchange(3,0xc4,b'',2)

    def test_amd_native_and_i2c_address_encoding(self):
        calls=[]
        def native(adapter,display,pointer):
            r=c.cast(pointer,c.POINTER(_NativeAuxRequest)).contents
            calls.append(('native',adapter,display,r.operation,r.address,bytes(r.data[:r.data_size])))
            r.result=0;r.data[0]=7;return 0
        def ddc(adapter,display,flag,option,size,tx,rxsize,rx):
            calls.append(('i2c',bytes(tx),c.cast(rxsize,c.POINTER(c.c_int)).contents.value))
            if rx is not None:rx[:]=b'R'*len(rx)
            return 0
        e=a.DriverEndpoint('amd',NS(_adl=NS(ADL_Display_NativeAUXChannel_Access=native,ADL_Display_DDCBlockAccess_Get=ddc)),port())
        self.assertEqual(e.exchange(1,0x400,b'',1),b'\x07')
        e.exchange(0,0x102,b'\xc0',1)
        e.exchange(5,0xc4,b'\x56\x00',2)
        self.assertEqual(e.exchange(6,0xc4,b'',2),b'RR')
        self.assertEqual(calls[0][1:5],(9,123,0,0x400))
        self.assertEqual(calls[1][3:],(1,0x102,b'\xc0'))
        self.assertEqual(calls[2],('i2c',b'\xc4\x56\x00',0))
        self.assertEqual(calls[3],('i2c',b'\xc5',2))

    def test_amd_failed_write_not_retried(self):
        transfer=Mock(return_value=-1)
        e=a.DriverEndpoint('amd',NS(_adl=NS(ADL_Display_DDCBlockAccess_Get=transfer)),port())
        with self.assertRaises(RuntimeError):e.exchange(2,0xc4,b'\xff\x10\x01',3)
        self.assertEqual(transfer.call_count,1)

    def test_linux_i2c_7bit_address_and_native_offsets(self):
        calls=[]
        def ioctl(fd,op,pointer):
            req=c.cast(pointer,c.POINTER(a.I2CRequest)).contents;m=req.messages[0]
            calls.append((fd,op,req.count,m.address,m.flags,m.length,bytes(m.buffer[:m.length])))
            if m.flags:c.memmove(m.buffer,b'L'*m.length,m.length)
            return 1
        e=a.LinuxEndpoint.__new__(a.LinuxEndpoint);e.aux_fd=10;e.i2c_fd=11;e.libc=NS(ioctl=ioctl)
        e.exchange(5,0xc4,b'\x56\x00',2)
        self.assertEqual(e.exchange(3,0xc4,b'',2),b'LL')
        self.assertEqual(calls[0],(11,0x0707,1,0x62,0,2,b'\x56\x00'))
        self.assertEqual(calls[1][3:6],(0x62,1,2))
        with patch.object(os,'pread',create=True,return_value=b'A') as read,patch.object(os,'pwrite',create=True,return_value=1) as write:
            self.assertEqual(e.exchange(1,0x400,b'',1),b'A');e.exchange(0,0x102,b'\x00',1)
            read.assert_called_once_with(10,1,0x400);write.assert_called_once_with(10,b'\x00',0x102)

    def test_linux_short_read_and_ioctl_failure(self):
        e=a.LinuxEndpoint.__new__(a.LinuxEndpoint);e.aux_fd=10;e.i2c_fd=11;e.libc=NS(ioctl=Mock(return_value=0))
        with self.assertRaises(RuntimeError):e.exchange(3,0xc4,b'',2)
        with patch.object(os,'pread',create=True,return_value=b''):
            with self.assertRaises(RuntimeError):e.exchange(1,0x400,b'',1)

    def test_linux_does_not_guess_i2c_bus_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);aux=root/'class/drm_dp_aux_dev/drm_dp_aux0';aux.mkdir(parents=True)
            (aux/'name').write_text('DP AUX')
            wrong=root/'class/i2c-adapter/i2c-0';wrong.mkdir(parents=True);(wrong/'name').write_text('DP AUX')
            pairs,errors=a.linux_pairs(root,root/'dev')
            self.assertEqual(pairs,[]);self.assertEqual(len(errors),1)

    def test_linux_pairs_siblings_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);aux=root/'class/drm_dp_aux_dev/drm_dp_aux2';aux.mkdir(parents=True)
            i2c=root/'class/i2c-adapter/i2c-9';i2c.mkdir(parents=True)
            for entry in (aux,i2c):(entry/'name').write_text('DP AUX')
            resolve=Path.resolve
            def mapped(path,*args,**kwargs):
                if path in (aux,i2c):return root/'devices/card0-DP-1'/path.name
                return resolve(path,*args,**kwargs)
            with patch.object(Path,'resolve',mapped):
                pairs,errors=a.linux_pairs(root,root/'dev')
                self.assertEqual(errors,[]);self.assertEqual(pairs[0][:2],(root/'dev/drm_dp_aux2',root/'dev/i2c-9'))
            extra=root/'class/i2c-adapter/i2c-10';extra.mkdir();(extra/'name').write_text('DP AUX')
            def ambiguous(path,*args,**kwargs):
                if path in (aux,i2c,extra):return root/'devices/card0-DP-1'/path.name
                return resolve(path,*args,**kwargs)
            with patch.object(Path,'resolve',ambiguous):
                pairs,errors=a.linux_pairs(root,root/'dev')
                self.assertEqual(pairs,[]);self.assertTrue(errors)

    def test_auto_uses_os_backends_and_isolates_unavailable_driver(self):
        calls=[]
        def add(pool,kind):
            calls.append(kind)
            if kind=='amd':raise RuntimeError('driver unavailable')
            pool.endpoints.append(NS(key=kind))
        with patch.object(a.Pool,'_add',add),patch.object(a.sys,'platform','win32'):
            pool=a.Pool()
            self.assertEqual(calls,['nvidia','amd','intel'])
            self.assertEqual([e.key for e in pool.endpoints],['nvidia','intel'])
            self.assertEqual(pool.errors[0]['backend'],'amd')
        calls.clear()
        with patch.object(a.Pool,'_add',add),patch.object(a.sys,'platform','linux'):
            a.Pool();self.assertEqual(calls,['linux'])
            with self.assertRaises(RuntimeError):a.Pool('intel')

    def test_protocol_rejects_unknown_writes_before_driver_call(self):
        endpoint=NS(number=42,key='test',backend='test',semantics='test',exchange=Mock())
        t=ProtocolTransport(endpoint)
        for fn,args in ((t.xfer,(0,0x480,b'\xff',1)),(t.xfer,(2,0xc4,b'\xff\x3c\xc3\xaa\x55',5)),
                        (t.lut_packet,(b'\x56\x00\x01',)),(t.range_command,(2,)),(t.select_bank,(8,))):
            with self.assertRaises(RuntimeError):fn(*args)
        endpoint.exchange.assert_not_called()

    def test_protocol_dispatches_all_table_packets_and_cleanup(self):
        calls=[]
        def exchange(cmd,address,data,n):calls.append((cmd,address,data,n));return data
        t=ProtocolTransport(NS(number=42,key='test',backend='test',semantics='test',exchange=exchange))
        with patch('lumalock.protocol.time.sleep'):
            t.range_command(1)
            for packet in profile.packets(profile.TARGET):t.lut_packet(packet)
            t.range_command(0);t.select_bank(0)
        self.assertEqual(len(calls),46)
        self.assertEqual(calls[0],(2,0xc4,b'\xff\x10\x01',3))
        self.assertEqual(calls[-1],(2,0xc4,b'\xff\x03\x00\x00',4))
        self.assertTrue(all(len(item[2])<=8 for item in calls))


if __name__=='__main__':unittest.main()
