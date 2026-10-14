"""Driver adapters. Addresses use 8-bit I2C write-address notation throughout.

Only the shared protocol layer issues operations in the CLI. No adapter retries
a failed write. AMD/Linux expose stopped I2C transactions, not raw MOT phases;
the same full firmware and LUT readback criteria must pass on those paths.
"""
import ctypes as c
import os
import stat
import sys
from pathlib import Path
from . import protocol as b


class Display(c.Structure):
    _fields_=[('version',c.c_uint32),('connector',c.c_uint32),('id',c.c_uint32),('flags',c.c_uint32)]


def nvidia_ids(t):
    enum=t.bind(0xe5ac921f,c.POINTER(c.c_void_p),c.POINTER(c.c_uint32))
    connected=t.bind(0x0078dba2,c.c_void_p,c.POINTER(Display),c.POINTER(c.c_uint32),c.c_uint32)
    gpus=(c.c_void_p*64)();count=c.c_uint32()
    b.require(enum(gpus,c.byref(count))==0 and count.value<=64,'NVIDIA GPU enumeration failed')
    found=set()
    for gpu in gpus[:count.value]:
        n=c.c_uint32()
        b.require(connected(gpu,None,c.byref(n),0)==0 and n.value<=64,'NVIDIA display enumeration failed')
        if not n.value:continue
        capacity=n.value;items=(Display*capacity)()
        for item in items:item.version=0x10010
        b.require(connected(gpu,items,c.byref(n),0)==0 and n.value<=capacity,'Display topology changed')
        for item in items[:n.value]:
            if item.flags & (1<<6) and item.flags & (1<<2) and not item.flags & (1<<1):found.add(item.id)
    return sorted(found)


class NvidiaSession:
    def __init__(self):
        self.nv=c.CDLL(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/nvapi64.dll'))
        self.nv.nvapi_QueryInterface.argtypes=[c.c_uint32]
        self.nv.nvapi_QueryInterface.restype=c.c_void_p
        self.init=self.bind(0x0150e828);self.unload=self.bind(0xd22bdd7e)
        self.aux=self.bind(0x8eb56969,c.c_uint32,c.POINTER(b.Request),c.c_uint32)
        b.require(self.init()==0,'NVAPI initialization failed')
    def bind(self,key,*args):
        pointer=self.nv.nvapi_QueryInterface(key)
        b.require(bool(pointer),f'Missing NVAPI entry {key:x}')
        return c.CFUNCTYPE(c.c_int,*args)(pointer)
    def close(self):self.unload()


class NvidiaEndpoint:
    backend='nvidia'
    semantics='raw-aux-mot'
    def __init__(self,session,number):
        self.session=session;self.number=number
        self.key=f'nvidia:0x{number:08X}'
    def exchange(self,cmd,address,data,n):
        req=b.Request();req.version=0x10028;req.display=self.number
        req.command=cmd;req.address=address;req.length=n-1;req.reply=0xffffffff
        req.data[:]=bytes([0xa5])*16;req.data[:len(data)]=data
        rc=self.session.aux(self.number,c.byref(req),c.sizeof(req))
        b.require(rc==0 and req.reply==0,f'NVIDIA AUX failed: {rc}/{req.reply}')
        return bytes(req.data[:n]) if cmd in (1,3,6) else data


class DriverEndpoint:
    def __init__(self,backend,session,port):
        self.backend=backend;self.session=session;self.port=port
        self.semantics='raw-aux-mot' if backend=='intel' else 'stopped-i2c'
        a=port.adapter
        # Intel handles are process-local. Use the OS encoder ID in recovery pins.
        output=port.physical_display_index if backend=='intel' else port.logical_display_index
        self.key=f'{backend}:{a.bus:02x}.{a.device:02x}.{a.function}:{output}'
        self.number=output

    def exchange(self,cmd,address,data,n):
        if self.backend=='intel':
            from .vendor.gpu_aux.intel import _CtlAuxAccessArgs
            req=_CtlAuxAccessArgs();req.Size=c.sizeof(req)
            req.OpType=1 if cmd in (1,3,6) else 2
            req.Flags=1 if cmd in (0,1) else (4 if cmd in (5,6) else 2)
            req.Address=address;req.DataSize=n;req.Data[:len(data)]=data
            rc=self.session._ctl.ctlAUXAccess(c.c_void_p(self.port.logical_display_index),c.byref(req))
            b.require(rc==0,f'Intel AUX failed: 0x{rc:08X}')
            b.require(req.DataSize==n,'Intel AUX returned a short transfer')
            return bytes(req.Data[:n]) if cmd in (1,3,6) else data
        from .vendor.gpu_aux.adl import _NativeAuxRequest
        if cmd in (0,1):
            req=_NativeAuxRequest();req.size=c.sizeof(req);req.operation=0 if cmd==1 else 1
            req.address=address;req.data_size=n;req.data[:len(data)]=data
            rc=self.session._adl.ADL_Display_NativeAUXChannel_Access(
                self.port.adapter.index,self.port.logical_display_index,c.byref(req))
            b.require(rc==0 and req.result==0,f'AMD AUX failed: {rc}/{req.result}')
            b.require(req.data_size==n,'AMD AUX returned a short transfer')
            return bytes(req.data[:n]) if cmd==1 else data
        read=cmd in (3,6)
        send=bytes([address | int(read)])+(b'' if read else data)
        tx=(c.c_uint8*len(send)).from_buffer_copy(send)
        rx=(c.c_uint8*n)() if read else None;size=c.c_int(n if read else 0)
        rc=self.session._adl.ADL_Display_DDCBlockAccess_Get(
            self.port.adapter.index,self.port.logical_display_index,0,0,len(send),tx,c.byref(size),rx)
        b.require(rc==0 and size.value==(n if read else 0),f'AMD I2C transfer failed/short: {rc}/{size.value}')
        return bytes(rx) if read else data


class I2CMessage(c.Structure):
    _fields_=[('address',c.c_uint16),('flags',c.c_uint16),('length',c.c_uint16),('buffer',c.POINTER(c.c_uint8))]


class I2CRequest(c.Structure):
    _fields_=[('messages',c.POINTER(I2CMessage)),('count',c.c_uint32)]


class LinuxEndpoint:
    backend='linux'
    semantics='stopped-i2c'
    def __init__(self,aux,i2c,identity):
        self.key='linux:'+identity;self.number=0;self.aux_fd=None;self.i2c_fd=None
        try:
            self.aux_fd=os.open(aux,os.O_RDWR|os.O_CLOEXEC)
            self.i2c_fd=os.open(i2c,os.O_RDWR|os.O_CLOEXEC)
            b.require(all(stat.S_ISCHR(os.fstat(fd).st_mode) for fd in (self.aux_fd,self.i2c_fd)),
                      'Linux AUX and I2C paths must be character devices')
            self.libc=c.CDLL(None,use_errno=True)
            self.libc.ioctl.argtypes=[c.c_int,c.c_ulong,c.c_void_p];self.libc.ioctl.restype=c.c_int
        except BaseException:self.close();raise
    def close(self):
        for name in ('aux_fd','i2c_fd'):
            fd=getattr(self,name,None)
            if fd is not None:os.close(fd);setattr(self,name,None)
    def exchange(self,cmd,address,data,n):
        if cmd==1:
            result=os.pread(self.aux_fd,n,address)
            b.require(len(result)==n,'Short Linux DPCD read');return result
        if cmd==0:
            b.require(os.pwrite(self.aux_fd,data,address)==n,'Short Linux DPCD write');return data
        read=cmd in (3,6);buffer=(c.c_uint8*n)()
        if not read:buffer[:]=data
        # i2c-dev uses 7-bit slave addresses, unlike the Windows bindings.
        message=I2CMessage(address>>1,int(read),n,buffer)
        request=I2CRequest(c.pointer(message),1)
        rc=self.libc.ioctl(self.i2c_fd,0x0707,c.byref(request)) # I2C_RDWR
        if rc<0:raise OSError(c.get_errno(),'Linux I2C_RDWR failed')
        b.require(rc==1,'Incomplete Linux I2C transaction')
        return bytes(buffer) if read else data


def linux_pairs(sysroot=Path('/sys'),devroot=Path('/dev')):
    """Pair only sibling AUX/I2C nodes with identical names. Never scan buses."""
    pairs=[];errors=[]
    for aux in sorted((sysroot/'class/drm_dp_aux_dev').glob('drm_dp_aux*')):
        try:
            parent=aux.resolve().parent;name=(aux/'name').read_text().strip()
            candidates=[i for i in (sysroot/'class/i2c-adapter').glob('i2c-*')
                        if i.resolve().parent==parent and (i/'name').read_text().strip()==name]
            b.require(len(candidates)==1,'Cannot uniquely pair AUX with its I2C adapter')
            i2c=candidates[0]
            # Pin both physical sysfs routes; don't infer that equal node numbers pair.
            identity=str(aux.resolve())+'|'+str(i2c.resolve())
            pairs.append((devroot/aux.name,devroot/i2c.name,identity))
        except (OSError,RuntimeError) as exc:errors.append(f'{aux.name}: {exc}')
    return pairs,errors


class Pool:
    def __init__(self,backend='auto'):
        self.endpoints=[];self.errors=[];self.owners=[]
        b.require(c.sizeof(c.c_void_p)==8,'64-bit Python is required')
        choices=('nvidia','amd','intel') if sys.platform=='win32' else ('linux',) if sys.platform.startswith('linux') else ()
        b.require(bool(choices),'Supported operating systems: Windows and Linux')
        if backend!='auto':
            b.require(backend in choices,f'{backend} backend is unavailable on {sys.platform}')
            choices=(backend,)
        for kind in choices:
            start=len(self.endpoints)
            try:self._add(kind)
            except Exception as exc:
                del self.endpoints[start:]
                self.errors.append({'backend':kind,'reason':str(exc)})
        keys=[e.key for e in self.endpoints]
        if len(keys)!=len(set(keys)):
            self.close();raise RuntimeError('Ambiguous driver endpoint identities')
    def _add(self,kind):
        if kind=='linux':
            pairs,errors=linux_pairs()
            self.errors.extend({'backend':kind,'reason':x} for x in errors)
            for args in pairs:
                try:
                    endpoint=LinuxEndpoint(*args);self.owners.append(endpoint);self.endpoints.append(endpoint)
                except Exception as exc:self.errors.append({'backend':kind,'reason':str(exc)})
            if not pairs and not errors:self.errors.append({'backend':kind,'reason':'No paired DRM AUX / I2C devices; check driver, CONFIG_DRM_DISPLAY_DP_AUX_CHARDEV and i2c-dev'})
            return
        if kind=='nvidia':
            session=NvidiaSession();self.owners.append(session)
            self.endpoints.extend(NvidiaEndpoint(session,n) for n in nvidia_ids(session));return
        if kind=='amd':
            from .vendor.gpu_aux.adl import AmdAux
            session=AmdAux()
        else:
            from .vendor.gpu_aux.intel import IntelAux
            session=IntelAux()
        self.owners.append(session)
        for adapter in session.adapters():
            for port in session.ports(adapter):self.endpoints.append(DriverEndpoint(kind,session,port))
    def close(self):
        for owner in reversed(self.owners):
            try:owner.close()
            except Exception:pass
        self.owners=[]
