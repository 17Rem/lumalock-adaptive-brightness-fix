"""Apply the optically confirmed factory high LUT, or restore the original LUT.

Volatile RAM only. Reuses exact short packets, identity checks, readback and
independent recovery from the successful temporary high-LUT experiment.
"""
import sys, time, json, uuid, hashlib, subprocess, argparse
from pathlib import Path
from . import compatibility, profile as p, protocol as b, runtime as runtime_platform
STATE_ROOT=runtime_platform.state_dir()

def known_table(t):
    accepted=[]
    for packet in (16,8):
        previous=None; consecutive=0
        for _ in range(b.TABLE_READ_ATTEMPTS):
            data=t.table(packet)
            consecutive=consecutive+1 if data==previous else 1
            previous=data
            if consecutive==3:break
        b.require(consecutive==3,'Unstable whole-table read')
        accepted.append(data)
    b.require(accepted[0]==accepted[1],'Independent whole-table reads disagree')
    b.require(accepted[0] in (p.ORIGINAL,p.TARGET),'Unrecognized current curve; no LUT written')
    return accepted[0]

def window_ok(r):
    return r.get('restricted_window_observed') is True and r.get('native_restored') is True and r.get('baseline_after')==p.BASELINE.hex()

def recover(t,state):
    if state['range_opened']:
        return b.recovery(t,state['lut_write_started'])
    return compatibility.close_preflight(t,state['bank_started'])

def guard(path):
    b.require(not sys.flags.optimize,'Optimized Python is unsupported; unset PYTHONOPTIMIZE')
    while True:
        state=json.loads(path.read_text(encoding='utf-8'))
        if state['done']:return
        if time.time()>=state['deadline']:break
        time.sleep(.25)
    t=None;report={}
    try:
        if state['lut_write_started']:
            p.install_tables(bytes.fromhex(state['original_lut']),bytes.fromhex(state['high_lut']))
        t=compatibility.Transport(pin=state['target_pin'])
        t.xfer(0,0x102,b'\xc0')
        # Pin the backend/endpoint + EDID + sink; never reuse Intel process handles.
        # Never rediscover a different matching screen during recovery.
        report=recover(t,state)
    except Exception as exc:report['error']=str(exc)
    finally:
        if t:t.unload()
        b.atomic_json(path.with_name(path.stem+'-recovery.json'),report)

def run(action,display_id=None,backend='auto'):
    b.require(action in ('apply','restore','check'),'Unsupported action')
    b.require(not sys.flags.optimize,'Optimized Python is unsupported; unset PYTHONOPTIMIZE')
    report={'action':action,'flash_writes':False,'success':False}
    tag=uuid.uuid4().hex[:12]
    STATE_ROOT.mkdir(parents=True,exist_ok=True)
    statepath=STATE_ROOT/f'brightness-control-{tag}-state.json'
    t=None; state=None; watch=None; write_started=False; armed=False
    lockfile=(STATE_ROOT/'brightness-control.lock').open('a+b')
    try:
        runtime_platform.lock(lockfile)
        t=compatibility.Transport(requested=display_id,backend=backend)
        report['target']=t.target_pin
        report['health_before']=t.health()
        b.require(report['health_before']['0x102']==0,'Unexpected link state; stop concurrent tests')
        state={'done':False,'deadline':time.time()+360,'lut_write_started':False,
               'bank_started':False,'range_opened':False,'target_pin':t.target_pin}
        b.atomic_json(statepath,state)
        watch=subprocess.Popen([sys.executable,'-X','utf8','-B','-m','lumalock','--guard',str(statepath)],
            cwd=str(p.ROOT),**runtime_platform.detached_options(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        armed=True;t.xfer(0,0x102,b'\xc0')
        print(f"已识别兼容候选屏幕 {t.target_pin.get('endpoint_id',hex(t.display))}，正在核验固件与原始曲线。",flush=True)
        def mark_bank():
            state['bank_started']=True;b.atomic_json(statepath,state)
        report['compatibility']=compatibility.verify_firmware(t,state['deadline']-180,mark_bank)
        target=p.TARGET if action=='apply' else p.ORIGINAL
        state['original_lut']=p.ORIGINAL.hex();state['high_lut']=p.TARGET.hex()
        b.atomic_json(statepath,state)
        b.require(b.restricted(t),'Unexpected initial query window')
        b.stable(t,0xc20,4,p.BASELINE)
        state['range_opened']=True;b.atomic_json(statepath,state)
        t.range_command(1)
        current=known_table(t)
        report['before']='fixed_high' if current==p.TARGET else 'original'
        print('已核对显示器及当前曲线。',flush=True)
        backup=STATE_ROOT/f"device-original-lut-{t.target_pin['edid_sha256']}.bin"
        if backup.exists():b.require(backup.read_bytes()==p.ORIGINAL,'Per-device original backup differs')
        else:backup.write_bytes(p.ORIGINAL)
        report['original_lut_backup']=backup.name
        if action!='check' and current!=target:
            write_started=True;state['lut_write_started']=True;b.atomic_json(statepath,state)
            print('正在设置，请等待约一分钟，不要同时运行其他屏幕工具。',flush=True)
            for packet in p.packets(target):
                b.require(time.time()<state['deadline']-90,'Insufficient rollback reserve')
                t.lut_packet(packet)
            b.verified_table(t,target)
            current=target
        report['after']='fixed_high' if current==p.TARGET else 'original'
        report['table_sha256']=hashlib.sha256(current).hexdigest()
        report['verified_0c28']=b.stable(t,0xc28,2).hex()
        report['window_recovery']=b.restore_window(t)
        b.require(window_ok(report['window_recovery']),'Query window cleanup incomplete')
        report['health_after']=t.health()
        b.require(report['health_after']==report['health_before'],'Link health changed')
        report['success']=True
    except Exception as exc:
        report['error']=str(exc)
        if t and armed:
            # Re-initialize in case failure occurred after the normal close.
            try:
                t.xfer(0,0x102,b'\xc0')
                report['rollback']=recover(t,state)
            except Exception as recovery_error:report['rollback_error']=str(recovery_error)
    finally:
        if state:
            state['done']=report['success'] or report.get('rollback',{}).get('restored',False)
            b.atomic_json(statepath,state)
        if t:report['transactions']=t.rows;t.unload()
        if watch and state and state['done']:watch.terminate();watch.wait(timeout=3)
        log=STATE_ROOT/f'brightness-control-{tag}.json'
        b.atomic_json(log,report)
        lockfile.close()
    if report['success']:
        if action=='check':
            print('核验通过，未改写亮度表；当前为'+('固定高亮度。' if report['after']=='fixed_high' else '原始亮度曲线。'),flush=True)
        else:
            print('固定高亮度已启用；不会按倒计时恢复。' if report['after']=='fixed_high' else '原始亮度曲线已恢复。',flush=True)
            print('不写固件。断电、休眠或重新连接后若效果消失，可重新运行固定高亮度。',flush=True)
    else:
        print('未完成：'+report.get('error','未知错误'),flush=True)
        print('已恢复原曲线。' if report.get('rollback',{}).get('restored') and write_started else '请查看恢复记录；不要连续重试。',flush=True)
    print('记录：'+str(log),flush=True)
    return report

def main():
    b.require(not sys.flags.optimize,'Optimized Python is unsupported; unset PYTHONOPTIMIZE')
    if len(sys.argv)==3 and sys.argv[1]=='--guard':guard(Path(sys.argv[2]));return
    parser=argparse.ArgumentParser(description='LumaLock: 固定匹配便携屏的亮度 / portable monitor brightness lock')
    parser.add_argument('action',choices=('list','apply','restore','check'))
    parser.add_argument('--display',help='Use the full endpoint identity shown by list')
    parser.add_argument('--backend',choices=('auto','nvidia','amd','intel','linux'),default='auto')
    args=parser.parse_args()
    if args.action=='list':
        try:
            rows=compatibility.list_displays(args.backend)
            for row in rows:
                print(row['display']+'  '+('候选屏幕；运行 check 核验固件 / candidate; run check' if row['candidate'] else row.get('reason','不兼容')))
            if not rows:print('No accessible DisplayPort / eDP interfaces found.')
        except Exception as exc:print('Enumeration failed: '+str(exc));raise SystemExit(1)
    else:raise SystemExit(0 if run(args.action,args.display,args.backend)['success'] else 1)
