"""K810 Light-tab fields; updates preserve unrelated packed fields."""
from .protocol import CONFIG_SIZE

MODES = ['off', 'breathing', 'constant', 'response', 'neon', 'ambilight',
         'comet-tail', 'single-water', 'flow-water', 'flashing',
         'monochromatic-wave', 'partition', 'combination']


def bounded(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer in {minimum}..{maximum}')
    return value


def decode_lighting(data):
    if len(data) != CONFIG_SIZE:
        raise ValueError('Expected configuration snapshot')
    colors = []
    for i in range(7):
        p = 1+2*i
        colors.append([255-16*(data[p]>>4), 255-16*(data[p+1]&15), 255-16*(data[p]&15)])
    return dict(mode=MODES[data[0x19]&15] if data[0x19]&15 < len(MODES) else 'unknown',
                mode_code=data[0x19]&15, brightness=6-((data[0x18]>>3)&7),
                speed=data[0x18]&7, direction=data[0x18]>>6,
                symmetry=bool(data[0x19]&128), color_selection=(data[0x19]>>4)&7,
                colors_enabled=data[0x1a]&127, colors=colors,
                reaction_type=data[15]&3)


def set_lighting(data, changes):
    result=bytearray(data)
    if len(result)!=CONFIG_SIZE or not isinstance(changes,dict):
        raise ValueError('Expected configuration and lighting object')
    allowed={'mode','brightness','speed','direction','symmetry','color_selection','colors_enabled','colors','reaction_type'}
    if set(changes)-allowed:
        raise ValueError('Unknown lighting fields')
    for name,value in changes.items():
        if name=='mode':
            if value not in MODES: raise ValueError('Unknown lighting mode')
            result[0x19]=(result[0x19]&0xf0)|MODES.index(value)
        elif name in ('brightness','speed','direction'):
            v=bounded(value,0,3 if name=='direction' else 6,name)
            mask,shift = (0x38,3) if name=='brightness' else (0xc0,6) if name=='direction' else (7,0)
            if name=='brightness': v=6-v
            result[0x18]=(result[0x18]&~mask)|(v<<shift)
        elif name=='symmetry':
            if type(value) is not bool: raise ValueError('symmetry must be boolean')
            result[0x19]=(result[0x19]&127)|(128 if value else 0)
        elif name=='color_selection':
            result[0x19]=(result[0x19]&0x8f)|(bounded(value,0,7,name)<<4)
        elif name=='colors_enabled':
            result[0x1a]=(result[0x1a]&128)|bounded(value,1,127,name)
        elif name=='reaction_type':
            result[15]=(result[15]&0xfc)|bounded(value,0,3,name)
        elif name=='colors':
            if not isinstance(value,list) or len(value)!=7: raise ValueError('Expected seven RGB colors')
            for i,rgb in enumerate(value):
                if not isinstance(rgb,list) or len(rgb)!=3: raise ValueError('Expected RGB triplet')
                r,g,b=[(255-bounded(c,0,255,'RGB channel'))//16 for c in rgb]
                p=1+2*i
                result[p]=(r<<4)|b
                result[p+1]=(result[p+1]&0xf0)|g
    return bytes(result)


def lighting_blocks(before, after):
    masks={i:(255 if i%2 else 15) for i in range(1,15)}
    masks.update({15:3,0x18:255,0x19:255,0x1a:127})
    if len(before)!=CONFIG_SIZE or len(after)!=CONFIG_SIZE or any((a^b)&~masks.get(i,0) for i,(a,b) in enumerate(zip(before,after))):
        raise ValueError('Lighting edit changes unrelated fields')
    offsets=[i for i in (0,8,0x18) if before[i:i+8]!=after[i:i+8]]
    if offsets and 0 not in offsets: offsets.insert(0,0)
    return [(i,after[i:i+8]) for i in offsets]
