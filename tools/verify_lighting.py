"""Generate Light-tab reference blocks with the original x86 Apply handler."""
import json, sys
from pathlib import Path
from trace_vendor_apply import trace
from verify_vendor import KNOWN_SHA256


def capture(executable, fields):
    state={0x6475f8:fields['mode_code'],0x6474c8:fields['direction'],
           0x6474cc:6-fields['brightness'],0x6474d0:fields['speed'],
           0x6474c4:int(fields['symmetry']),0x63dd40:fields['color_selection'],
           0x6475b8:fields['reaction_type'],0x61f108:1}
    for i in range(7):
        state[0x64759c+i*4]=(fields['colors_enabled']>>i)&1
        for j,c in enumerate(fields['colors'][i]):state[0x6474d8+i*12+j*4]=(255-c)//16
    for i in range(9):state[0x6475c4+i*4]=1
    writes=[e for e in trace(executable,state=state) if 'write_address' in e]
    return {'fields':fields,'blocks':[w for w in writes if 0xe0<=w['write_address']<0x100]}


if __name__=='__main__':
    source=Path(sys.argv[1]).read_bytes()
    defaults=dict(mode_code=2,brightness=6,speed=3,direction=0,symmetry=False,
                  color_selection=1,colors_enabled=127,reaction_type=0,
                  colors=[[255,15,15],[15,255,15],[15,15,255],[255,255,15],
                          [255,15,255],[15,255,255],[255,255,255]])
    cases=[dict(defaults,mode_code=i) for i in range(13)]
    cases += [dict(defaults,brightness=i,speed=6-i) for i in range(7)]
    cases += [dict(defaults,mode_code=8,direction=i,symmetry=True,color_selection=3,colors_enabled=85,reaction_type=i) for i in range(4)]
    cases += [dict(defaults,colors=[[255-16*((i*3+j)%16) for j in range(3)] for i in range(7)])]
    output={'source_sha256':KNOWN_SHA256,'cases':[capture(source,c) for c in cases]}
    Path('tests/vendor_lighting_vectors.json').write_text(json.dumps(output,indent=2)+'\n')
    print(f'Generated {len(cases)} Light-tab fixtures from original x86')
