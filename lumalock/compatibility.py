"""Discover matching panels and verify live bytes against public fingerprints."""
import hashlib
import time
from . import protocol as b, profile, backends as aux_backends
from .protocol import ProtocolTransport

def read_edid(t):
    copies=[]
    for method in ('settled','split'):
        previous=None;count=0
        for _ in range(10):
            data=b''.join(t.read_at(0xa0,offset,16,method) for offset in range(0,128,16))
            count=count+1 if data==previous else 1;previous=data
            if count==3:break
        b.require(count==3,'EDID read is unstable')
        copies.append(data)
    b.require(copies[0]==copies[1],'Independent EDID reads disagree')
    return copies[0]

def edid_matches(data):
    if len(data)!=128 or data[:8]!=bytes.fromhex('00ffffffffffff00') or sum(data)%256:return False
    if data[8:12]!=bytes.fromhex(profile.DATA['edid_product']):return False
    names=[data[i+5:i+18].decode('ascii',errors='replace').strip() for i in range(54,126,18) if data[i:i+5]==bytes.fromhex('000000fc00')]
    # Serial number, manufacture date and checksum can vary between units.
    return names==[profile.DATA['model']]

def inventory(pool):
    rows=[]
    for endpoint in pool.endpoints:
        t=ProtocolTransport(endpoint)
        row={'display_id':endpoint.number,'display':endpoint.key,'endpoint_id':endpoint.key,
             'backend':endpoint.backend,'semantics':endpoint.semantics,'candidate':False}
        try:
            identities=[t.identity() for _ in range(3)]
            b.require(all(x==b.EXPECTED_SINK for x in identities),'Unsupported sink/controller')
            edid=read_edid(t);b.require(edid_matches(edid),'Unsupported EDID/model')
            row.update(candidate=True,profile=profile.DATA['id'],edid=edid.hex(),edid_sha256=hashlib.sha256(edid).hexdigest(),sink=identities[0].hex())
        except Exception as exc:row['reason']=str(exc)
        rows.append(row)
    return rows


def choose(rows,requested=None,pin=None):
    matches=[row for row in rows if row['candidate']]
    if pin is not None:
        keys=('backend','endpoint_id','edid_sha256','sink')
        b.require(all(k in pin for k in keys),'Recovery pin lacks backend/endpoint identity')
        matches=[r for r in matches if all(r.get(k)==pin[k] for k in keys)]
        b.require(len(matches)==1,'Recovery target missing or changed; refusing to select another display')
    elif requested is not None:
        if isinstance(requested,int) or str(requested).lower().startswith('0x'):
            number=requested if isinstance(requested,int) else int(requested,0)
            matches=[r for r in matches if r['backend']=='nvidia' and r['display_id']==number]
        else:matches=[r for r in matches if r['endpoint_id']==requested]
        b.require(len(matches)==1,'Requested display is not a compatible candidate')
    else:
        b.require(bool(matches),'No compatible NE180QDM-NZ4 / NT71873 candidate found')
        b.require(len(matches)==1,'Multiple compatible candidates; use list then --display ENDPOINT_ID')
    return matches[0]


class Transport(ProtocolTransport):
    def __init__(self,requested=None,pin=None,backend='auto'):
        if pin is not None:backend=pin['backend']
        self.pool=aux_backends.Pool(backend)
        try:
            rows=inventory(self.pool)
            if not any(r['candidate'] for r in rows) and self.pool.errors:
                details='; '.join(e['backend']+': '+e['reason'] for e in self.pool.errors)
                raise RuntimeError('No compatible candidate. Backend diagnostics: '+details)
            chosen=choose(rows,requested,pin)
            endpoint=next(e for e in self.pool.endpoints if e.key==chosen['endpoint_id'])
            super().__init__(endpoint)
            self.discovery=rows;self.backend_errors=self.pool.errors
            self.panel_edid=bytes.fromhex(chosen['edid'])
            self.target_pin={key:chosen[key] for key in ('backend','endpoint_id','display_id','edid_sha256','sink')}
            b.require(self.identity()==b.EXPECTED_SINK,'Panel identity changed after selection')
        except BaseException:
            self.pool.close();raise
    def unload(self):self.pool.close()


def expected_block(t,offset,size,expected_hash,deadline):
    count=0
    for _ in range(20):
        b.require(time.time()<deadline,'Firmware verification deadline reached')
        value=t.read_burst(0xc4,offset,size,.02)
        count=count+1 if profile.digest(value)==expected_hash else 0
        if count==3:return value
    raise RuntimeError(f'Firmware profile mismatch or unstable read at window {offset:04X}')


def verify_firmware(t,deadline,bank_started=lambda:None):
    blocks=profile.DATA['blocks']
    expected_block(t,0xd000,256,blocks['000000']['full'],deadline)
    bank_started();previous_page=None;curves={};code=bytearray()
    for key,hashes in blocks.items():
        address=int(key,16);page=address//4096;offset=0xd000+address%4096
        if page!=previous_page:t.select_bank(page);previous_page=page
        full=expected_block(t,offset,256,hashes['full'],deadline)
        first=expected_block(t,offset,128,hashes['first'],deadline)
        second=expected_block(t,offset+128,128,hashes['second'],deadline)
        b.require(full==first+second,'Independent firmware reads disagree')
        if address<0x8000:code.extend(full)
        else:curves[address]=full
    b.require(len(code)==0x8000 and profile.digest(code)==profile.DATA['code_sha256'],'Full code fingerprint mismatch')
    t.select_bank(0);expected_block(t,0xd000,256,blocks['000000']['full'],deadline)
    profile.install_tables(curves[0x29f00],curves[0x29e00])
    return {'profile':profile.DATA['id'],'code_sha256':profile.DATA['code_sha256'],
            'code_bytes':len(code),'factory_tables_verified':True,'marker':profile.DATA['firmware_marker']}


def close_preflight(t,bank_started):
    result={}
    try:
        if bank_started:
            t.select_bank(0);expected_block(t,0xd000,256,profile.DATA['blocks']['000000']['full'],time.time()+10)
        result['bank_zero_restored']=True
    except Exception as exc:result['bank_error']=str(exc)
    finally:
        try:t.xfer(0,0x102,b'\x00');result['native_restored']=t.native(0x102)==0
        except Exception as exc:result['native_error']=str(exc)
    result['restored']=result.get('bank_zero_restored',False) and result.get('native_restored',False)
    return result


def list_displays(backend='auto'):
    pool=aux_backends.Pool(backend)
    try:
        rows=inventory(pool)
        rows.extend({'display':e['backend'],'backend':e['backend'],'candidate':False,
                     'reason':e['reason'],'backend_unavailable':True} for e in pool.errors)
        return rows
    finally:pool.close()
