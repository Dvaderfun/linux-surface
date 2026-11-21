#!/usr/bin/python3
"""Check the SL1 IR emitter using hardware alternate frames and two negative controls."""
import argparse
from pathlib import Path
import json
import math
import os
import sys
from discover import discover
import signal
import statistics as S
import subprocess as sp
import tempfile

HERE = Path(__file__).resolve().parent
CENTER = [y*8+x for y in range(1,5) for x in range(1,7)]
NAMES = ('off_before', 'on', 'off_after')

def ports():
    # Reuse the bridge's read-only discovery, including disabled links.
    if Path('/sys/class/dmi/id/product_sku').read_text().strip() != 'Surface_Laptop' or \
            Path('/sys/class/dmi/id/sys_vendor').read_text().strip() != 'Microsoft Corporation':
        raise ValueError("This optical check is for the original Microsoft Surface Laptop only.")
    return discover()

def percentile(xs,q):
    return sorted(xs)[round(q*(len(xs)-1))]

def analyze(data):
    first, during, last = groups = [[x for x in data['frames'] if x['phase']==k] for k in range(3)]
    if not data['restored'] or not all(len(g)==20 for g in groups):
        raise ValueError("incomplete stream or controls were not restored")
    timing = {}
    for name,g in zip(NAMES,groups):
        ds=[b['sequence']-a['sequence'] for a,b in zip(g,g[1:])]
        dt=[b['timestamp_us']-a['timestamp_us'] for a,b in zip(g,g[1:])]
        if any(z!=1 for z in ds) or min(dt)<=0:
            raise ValueError(f'{name}: dropped/duplicate frames or timestamps')
        timing[name]={'first_sequence':g[0]['sequence'],'last_sequence':g[-1]['sequence'],
                      'fps':round(1e6/S.median(dt),2)}
    # A tile is accepted only if it was not clipped in any phase/parity.
    tiles=[i for i in CENTER if all(S.median([x['clipped'][i] for x in g if x['sequence']%2==p])<=40
               for g in groups for p in (0,1))]
    if len(tiles)<6: raise ValueError('too few unsaturated central tiles; ambient light may be too bright')
    def even_odd(g, sample):
        # Positive means even frames are brighter. Interpolation cancels a local linear scene trend.
        out=[]
        for a,b,c in zip(g,g[1:],g[2:]):
            out.append((sample(b)-(sample(a)+sample(c))/2)*(-1 if b['sequence']%2 else 1))
        return out
    ans = []
    for t in tiles:
        ds=[even_odd(g,lambda x:x['means'][t]) for g in groups]
        on=S.median(ds[1]); off=ds[0]+ds[2]
        limit=max(3.0,4*percentile([abs(v) for v in off],.9))
        sign=1 if on>0 else -1
        stable=sum(sign*x>limit/2 for x in ds[1])/len(ds[1])
        ans.append((t,on,limit,stable))
    strength = {p:sum(1 for i,on,limit,s in ans if p*on>limit and s>=.85) for p in (1,-1)}
    sign=max((1,-1),key=strength.get)
    vals=lambda x:S.mean(x['means'][i] for i in tiles)
    d=[even_odd(g,vals) for g in groups]; on=S.median(d[1])*sign
    ctrl=max(percentile([abs(z) for z in d[0]],.9),percentile([abs(z) for z in d[2]],.9))
    lit = [vals(x) for x in during if (x['sequence']%2==0)==(sign==1)]
    dark = [vals(x) for x in during if (x['sequence']%2!=0)==(sign==1)]
    ambient=[S.median(vals(x) for x in g) for g in [first,last]]
    # The unlit phase must return to the ambient range, and the bright phase
    # exceed both off phases. Allows small genuine drift when the room changes.
    zero_dist=min(abs(S.median(dark)-a) for a in ambient)
    stable_on=sum(sign*z>max(1,ctrl) for z in d[1])/len(d[1])
    checks={'coherent_spatial_response':strength[sign]>=max(4,math.ceil(.25*len(tiles))) and strength[-sign]<=1,
            'alternation_exceeds_off_controls':on>max(3,4*ctrl) and stable_on>=.85,
            'dark_phase_near_ambient':zero_dist<=max(6,.55*on),
            'lit_phase_brighter_than_off':S.median(lit)>max(ambient)+max(2,.25*on)}
    return dict(verified=all(checks.values()),checks=checks,controls={'strobe_schedule':[0,1,0],
                'exposure_lines':data['exposure_lines'],'analogue_gain_register':data['gain_register'],
                'original_exposure':data['original_exposure'],'original_gain':data['original_gain'],
                'original_strobe':data['original_strobe'],'restored':data['restored']},
                timings=timing,units='10-bit raw DN; matched central sensor coordinates',
                central_tiles_used=len(tiles),same_phase_responding_tiles=strength[sign],opposite_phase_tiles=strength[-sign],
                threshold_pass_fraction=round(stable_on,3),lit_sequence_parity='even' if sign==1 else 'odd',
                center_means_DN=dict(zip(('off_before','on_lit','on_dark','off_after'),map(lambda x:round(x,3),[ambient[0],S.median(lit),S.median(dark),ambient[1]]))),
                signal_delta_DN=round(on,3),control_parity_p90_abs_DN=round(ctrl,3),
                off_even_minus_odd_DN=[round(S.median(d[0]),3),round(S.median(d[2]),3)],
                sampled_raw_bits=10)

def synthetic(mode):
    d={'restored':True,'original_gain':16,'original_exposure':504,'original_strobe':0,
       'exposure_lines':400,'gain_register':128,'frames':[]}
    for phase in range(3):
        for j in range(20):
            n=phase*28+j+8
            if mode=='good': extra=35 if phase==1 and n%2 else 0
            elif mode=='ignored': extra=0
            elif mode=='ambient_flicker': extra=35 if n%2 else 0
            elif mode=='dc': extra=35 if phase==1 else 0
            else: raise ValueError(mode)
            d['frames'].append(dict(phase=phase,sequence=n,timestamp_us=33333*n,
                               means=[43+.02*n+.04*i+extra for i in range(48)],clipped=[0]*48))
    return d

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--self-test',action='store_true',help='synthetic controls; no device access')
    p.add_argument('--also-color',action='store_true',help='also run the companion PipeWire color test, after the IR sensor is closed')
    args=p.parse_args()
    if args.self_test:
        for mode in ('good','ignored','ambient_flicker','dc'):
            z=analyze(synthetic(mode));assert z['verified']==(mode=='good'), (mode,z)
        print('PASS: true odd-phase strobe accepted; ignored control, external flicker and constant offset rejected.')
    else:
        try:
            paths=ports()
            video,sensor=paths[:2]
            with tempfile.TemporaryDirectory(prefix='sl1-ir-probe-',dir=os.environ.get('XDG_RUNTIME_DIR')) as tmp:
                binary=str(Path(tmp)/'probe')
                sp.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(HERE/'probe.c'),'-o',binary],check=True)
                # On interruption let the native collector disable the emitter and
                # restore controls; do not immediately SIGKILL its finally path.
                def interrupted(sig,frame): raise KeyboardInterrupt
                for sig in (signal.SIGTERM,signal.SIGHUP): signal.signal(sig,interrupted)
                proc=sp.Popen([binary,*paths],stdout=sp.PIPE,stderr=sp.PIPE,text=True,start_new_session=True)
                try:
                    out,err=proc.communicate(timeout=12)
                except BaseException:
                    proc.terminate()
                    try: proc.communicate(timeout=4)
                    except sp.TimeoutExpired:
                        proc.kill();proc.communicate()
                    raise
                if proc.returncode: raise RuntimeError(err.strip() or f'raw probe exit {proc.returncode}')
                result=analyze(json.loads(out))
            result['video']=video; result['sensor']=sensor
            if args.also_color:
                cp=sp.run([sys.executable, str(HERE / 'capture.py')],capture_output=True,text=True,timeout=18)
                result['color_passed']=cp.returncode==0; result['color_result']=(cp.stdout+cp.stderr).strip()
            print(json.dumps(result,indent=2))
            raise SystemExit(0 if result['verified'] and result.get('color_passed',True) else 1)
        except (ValueError,RuntimeError,OSError,sp.SubprocessError) as e: raise SystemExit(str(e))
