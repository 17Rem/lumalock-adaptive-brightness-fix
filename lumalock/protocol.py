"""Shared bounded panel protocol. No firmware image or arbitrary write API."""
import ctypes as c
import json
import os
import threading
import time
from . import profile
from .progress import emit

EXPECTED_SINK=bytes.fromhex(profile.DATA['sink'])
NATIVE_READS={0x102,0x700,0x701,0x702,0x720,0x721,*range(0x400,0x409)}
WINDOWS={0x0500:16,0x0c20:4,0x0c28:2,0x5600:1}
TABLE_READ_ATTEMPTS=20


def require(ok,message):
    if not ok:raise RuntimeError(message)


def atomic_json(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,path)


def allowed(cmd,addr,data,n):
    if not 1<=n<=16:return False
    if cmd==1:return addr in NATIVE_READS and n==1 and not data
    if cmd==0:return addr==0x102 and n==1 and data in (b'\x00',b'\xc0')
    if cmd in (3,6):return addr in (0xa0,0xc4) and not data
    if cmd in (2,5):
        if len(data)!=n:return False
        if addr==0xa0:return n==1 and data[0]<128
        if addr==0xc4 and n==2:
            offset=int.from_bytes(data,'big')
            return 0xd000<=offset<0xe000 or (cmd==5 and any(a<=offset<a+s for a,s in WINDOWS.items()))
    return False


class Request(c.Structure):
    _fields_=[('version',c.c_uint32),('display',c.c_uint32),('command',c.c_uint32),('address',c.c_uint32),
              ('data',c.c_uint8*16),('length',c.c_uint32),('reply',c.c_uint32),('reserved',c.c_uint8*64)]
require(c.sizeof(Request)==104,'Unexpected NVAPI structure size')


class ProtocolTransport:
    def __init__(self,endpoint):
        self.endpoint=endpoint;self.display=endpoint.number;self.display_label=endpoint.key
        self.rows=[];self.lock=threading.RLock()

    def _exchange(self,cmd,address,data=b'',n=1):
        row={'backend':self.endpoint.backend,'semantics':self.endpoint.semantics,
             'cmd':cmd,'address':hex(address),'tx':data.hex(),'length':n}
        start=time.perf_counter_ns()
        try:
            value=self.endpoint.exchange(cmd,address,data,n)
            require(len(value)==n,'Backend returned a short transfer')
            row.update(status=0,reply=0,rx=value.hex());return value
        except Exception as exc:row['error']=str(exc);raise
        finally:
            row['elapsed_us']=(time.perf_counter_ns()-start)//1000;self.rows.append(row)

    def xfer(self,cmd,addr,data=b'',n=1):
        require(allowed(cmd,addr,data,n),'Request rejected by panel-operation allowlist')
        value=self._exchange(cmd,addr,data,n)
        if cmd==5 and addr==0xc4:time.sleep(.008)
        return value

    def native(self,addr):return self.xfer(1,addr)[0]
    def identity(self):return bytes(self.native(a) for a in range(0x400,0x409))
    def health(self):return {hex(a):self.native(a) for a in (0x102,0x700,0x701,0x702,0x720,0x721)}

    def read_at(self,device,offset,n,method):
        require(method in ('settled','split'),'Unsupported read method')
        if device==0xc4:
            require(any(a<=offset and offset+n<=a+s for a,s in WINDOWS.items()),'Read outside profile windows')
        pointer=bytes([offset]) if device==0xa0 else offset.to_bytes(2,'big')
        with self.lock:
            try:
                self.xfer(5,device,pointer,len(pointer));time.sleep(.002)
                if method=='split' and n>1:
                    first=n//2
                    return self.xfer(6,device,n=first)+self.xfer(3,device,n=n-first)
                return self.xfer(3,device,n=n)
            except Exception:
                try:self.xfer(3,device,n=1)
                except Exception:pass
                raise

    def read_burst(self,device,offset,n,settle=.02):
        require(device==0xc4 and n in (128,256) and 0xd000<=offset and offset+n<=0xe000,'Read outside firmware profile')
        return self._burst(device,offset,n,16,settle)

    def _burst(self,device,offset,n,packet,settle):
        with self.lock:
            try:
                self.xfer(5,device,offset.to_bytes(2,'big'),2);time.sleep(settle)
                result=bytearray()
                while len(result)<n:
                    size=min(packet,n-len(result))
                    result+=self.xfer(3 if len(result)+size==n else 6,device,n=size)
                return bytes(result)
            except Exception:
                try:self.xfer(3,device,n=1)
                except Exception:pass
                raise

    def table(self,packet):
        require(packet in (8,16),'Unsupported table packet size')
        return self._burst(0xc4,0x5600,256,packet,.15)

    def select_bank(self,page):
        require(page in (*range(8),0x29),'Read-window selection outside profile')
        self._exchange(2,0xc4,bytes([0xff,3,page//16,(page%16)*16]),4);time.sleep(.01)

    def range_command(self,value):
        require(value in (0,1),'Invalid range selector')
        time.sleep(.5);self._exchange(2,0xc4,bytes((0xff,0x10,value)),3);time.sleep(.5)

    def lut_packet(self,data):
        require(profile.packet_allowed(data) and len(data)<=8,'LUT write outside verified curve packets')
        time.sleep(.5);self._exchange(2,0xc4,data,len(data));time.sleep(.5)


def stable(t,address,size,expected=None):
    copies=[]
    for method in ('settled','split'):
        previous=None;count=0
        for _ in range(7):
            value=t.read_at(0xc4,address,size,method)
            count=count+1 if value==previous else 1;previous=value
            if count==3:break
            time.sleep(.005)
        require(count==3,f'Unstable {method} read at {address:04x}')
        copies.append(value)
    require(copies[0]==copies[1],'Independent register reads disagree')
    if expected is not None:require(copies[0]==expected,f'Unexpected value at {address:04x}')
    return copies[0]


def verified_table(t,expected):
    for packet in (16,8):
        count=0
        for _ in range(TABLE_READ_ATTEMPTS):
            count=count+1 if t.table(packet)==expected else 0
            if count==3:break
        require(count==3,'Whole LUT did not match expected table three times')
    return True


def restricted(t):
    expected=t.panel_edid[:16];stable(t,0x500,16,expected)
    return t.table(16)[:16]==expected


def restore_window(t):
    report={}
    try:
        t.range_command(0);report['restricted_window_observed']=restricted(t)
        report['baseline_after']=stable(t,0xc20,4,profile.BASELINE).hex()
    except Exception as exc:report['window_error']=str(exc)
    finally:
        try:t.xfer(0,0x102,b'\x00');report['native_restored']=t.native(0x102)==0
        except Exception as exc:report['native_error']=str(exc)
    return report


def window_ok(r):
    return r.get('restricted_window_observed') is True and r.get('native_restored') is True and r.get('baseline_after')==profile.BASELINE.hex()


def recovery(t,restore_lut,on_progress=None):
    report={}
    try:
        if restore_lut:
            t.range_command(1);errors=[]
            packets=profile.packets(profile.ORIGINAL)
            emit(on_progress,'recovery','正在恢复原始曲线',0,len(packets))
            for index,packet in enumerate(packets,1):
                try:t.lut_packet(packet)
                except Exception as exc:errors.append(str(exc))
                emit(on_progress,'recovery','正在恢复原始曲线（已尝试的数据包）',index,len(packets))
            emit(on_progress,'recovery','正在校验恢复结果')
            report['packet_errors']=errors;report['original_table_verified']=verified_table(t,profile.ORIGINAL)
    except Exception as exc:report['lut_restore_error']=str(exc)
    finally:report['window_recovery']=restore_window(t)
    report['restored']=(not restore_lut or report.get('original_table_verified',False)) and window_ok(report['window_recovery'])
    return report
