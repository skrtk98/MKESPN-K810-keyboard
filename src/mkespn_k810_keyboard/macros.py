"""K201 macro records and allocation. No vendor code is needed at runtime."""
import struct

from .protocol import CONFIG_SIZE, EEPROM_SIZE, KEYMAP_OFFSET, control_offset, keycode
from .lighting import MODES as LIGHT_MODES

MACRO_CODES = list(range(0xA5, 0xB0)) + list(range(0xB8, 0xC1))
BUTTONS = {'left': 0xF1, 'right': 0xF3, 'middle': 0xF2}
# Original skin buttons 10 (release) and 11 (click), handlers 416170/4161c1.
MODES = {'repeat': 0, 'while-held': 2, 'until-click': 1}


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')
    return value


def compile_macro(spec, address=0):
    """Return firmware payload, encoded event count and mode bits."""
    if not isinstance(spec, dict):
        raise ValueError('A macro must be a JSON object')
    mode = spec.get('mode', 'repeat')
    if mode not in MODES:
        raise ValueError('Unknown macro repeat mode')
    repeat = integer(spec.get('repeat', 1), 1, 65535, 'repeat')
    events = spec.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= 275:
        raise ValueError('A macro needs 1..275 events')
    result = bytearray(struct.pack('<H', repeat if mode == 'repeat' else 1))
    count = 0
    held = set()
    led_sections=[]
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('Invalid macro event')
        kind = event.get('type')
        milliseconds = integer(event.get('delay', 8), 8, 10000, 'delay')
        ticks = max(1, milliseconds // 8)
        # The original serializer emits a remainder event and 127-tick delay
        # records after it for delays longer than 1016ms.
        extension = ticks // 127 if ticks > 127 else 0
        remainder = max(1, ticks - extension * 127)
        if kind in ('key-down', 'key-up'):
            value=event.get('key')
            if type(value) is int:
                code=value
            elif isinstance(value,str):
                code=keycode(value)
            else:
                raise ValueError('Macro keys must be names or integer HID usages')
            if not (4 <= code <= 0xA4 or 0xE0 <= code <= 0xE7):
                raise ValueError('Macro key events need an ordinary keyboard key')
            down = kind == 'key-down'
            identity = ('key', code)
            result.extend((remainder | (0x80 if down else 0), code))
        elif kind in ('mouse-down', 'mouse-up'):
            if event.get('button') not in BUTTONS:
                raise ValueError('Mouse button must be left, right or middle')
            code = BUTTONS[event['button']]
            down = kind == 'mouse-down'
            identity = ('mouse', code)
            result.extend((remainder | (0x80 if down else 0), code))
        elif kind == 'scroll':
            steps = integer(event.get('steps'), -127, 127, 'scroll steps')
            result.extend((remainder, 0xF7, steps & 255, 0))
            identity = None
        elif kind == 'move':
            x = integer(event.get('x'), -32767, 32767, 'x')
            y = integer(event.get('y'), -32767, 32767, 'y')
            result.extend(bytes((remainder, 0xF6)) + struct.pack('<hh', x, y))
            identity = None
        elif kind == 'delay':
            result.extend((remainder, 0))
            identity = None
        elif kind == 'led':
            sequence=event.get('sequence')
            if not isinstance(sequence,list) or not 1<=len(sequence)<=16 or len(led_sections)>=5:
                raise ValueError('LED needs 1..16 pattern steps, at most five insertions')
            body=bytearray((len(sequence)-1,0,0,0))
            for step in sequence:
                if not isinstance(step,dict) or step.get('mode') not in LIGHT_MODES:
                    raise ValueError('Unknown LED sequence mode')
                color=integer(step.get('color',0),0,7,'LED color')
                duration=integer(step.get('duration_ms',1000),100,25500,'LED duration')//100
                body.extend((LIGHT_MODES.index(step['mode']),color,duration,1))
            led_sections.append((len(result),integer(event.get('behavior',0),0,2,'LED behavior'),body))
            result.extend((remainder,0xf9,0,0))
            identity=None
        else:
            raise ValueError(f'Unknown macro event: {kind}')
        if identity is not None:
            if down:
                held.add(identity)
            else:
                held.discard(identity)
        result.extend(b'\x7f\0' * extension)
        count += 1 + extension
    if held:
        raise ValueError('Every pressed key/mouse button must be released in the macro')
    result.extend(bytes((-len(result)) % 8))
    for position,behavior,body in led_sections:
        pointer=address+len(result)
        if pointer+len(body)>EEPROM_SIZE-0x48:
            raise ValueError('LED data is outside supported EEPROM region')
        result[position+2:position+4]=bytes((pointer&255,(pointer>>8)|(behavior<<6)))
        result.extend(body)
        result.extend(bytes((-len(result))%8))
    return bytes(result), count, MODES[mode]


def macro_entry(address, count, mode):
    integer(address, 0, EEPROM_SIZE-1, 'macro address')
    integer(count, 1, 16383, 'event count')
    if mode not in MODES.values():
        raise ValueError('Unknown mode')
    return bytes((7, (count & 127) | (128 if mode == 2 else 0),
                  address & 255, (address >> 8) | (128 if mode == 1 else 0), count >> 7))


def table_address(image, base):
    if len(image) != EEPROM_SIZE or image[0xD0:0xD2] != b'\xe1\x1e':
        raise ValueError('Expected a complete K810 EEPROM snapshot')
    if int.from_bytes(image[0xD2:0xD4], 'little') != base:
        raise ValueError('Configuration base does not match EEPROM header')
    table = int.from_bytes(image[base+30:base+32], 'little')
    if table != base + CONFIG_SIZE:
        raise ValueError('Unsupported macro table pointer')
    return table


def referenced_ranges(image, base, table):
    """Protect every macro referenced by any of the 160 matrix entries."""
    codes = set(image[base+KEYMAP_OFFSET:base+KEYMAP_OFFSET+160])
    slots = {MACRO_CODES.index(code) for code in codes if code in MACRO_CODES}
    ranges = []
    for slot in slots:
        record = image[table+slot*5:table+slot*5+5]
        if len(record) != 5 or record[0] != 7:
            raise ValueError('An existing referenced macro has an unknown format')
        count = (record[1] & 127) + (record[4] << 7)
        address = record[2] + ((record[3] & 63) << 8)
        if not table+104 <= address < EEPROM_SIZE-0x48:
            raise ValueError('Existing macro address is outside the supported region')
        end = address+2
        for _ in range(count):
            if end+2 > EEPROM_SIZE-0x48:
                raise ValueError('Existing macro is out of bounds')
            code = image[end+1]
            if code == 0xFB:
                raise ValueError('Existing GPIO macro allocation is not supported')
            if code == 0xF9:
                if end+4>EEPROM_SIZE-0x48:raise ValueError('LED reference is out of bounds')
                pointer=image[end+2]+((image[end+3]&63)<<8)
                if pointer<table+104 or pointer>=EEPROM_SIZE-0x48 or image[pointer]>15:
                    raise ValueError('LED sequence pointer/count is invalid')
                section_end=pointer+4+4*(image[pointer]+1)
                if section_end>EEPROM_SIZE-0x48:raise ValueError('LED sequence is out of bounds')
                ranges.append((pointer,(section_end+7)&~7))
            end += 6 if code == 0xF6 else 4 if code in (0xF7,0xF9,0xFA) else 2
        if end > EEPROM_SIZE-0x48:
            raise ValueError('Existing macro is out of bounds')
        ranges.append((address, (end+7)&~7))
    return slots, ranges


def plan_macro(image, base, control, spec):
    table = table_address(image, base)
    slots, ranges = referenced_ranges(image, base, table)
    slot = next((s for s in range(20) if s not in slots), None)
    if slot is None:
        raise ValueError('All 20 macro slots are referenced')
    payload, count, mode = compile_macro(spec)
    minimum = (table+104+7)&~7
    address = next((a for a in range(minimum, EEPROM_SIZE-0x48-len(payload)+1, 8)
                    if image[a:a+len(payload)] == b'\xff'*len(payload)
                    and not any(a < end and a+len(payload) > start for start,end in ranges)), None)
    if address is None:
        raise ValueError('No unused erased EEPROM region fits this macro')
    payload,count,mode=compile_macro(spec,address)
    after = bytearray(image)
    after[address:address+len(payload)] = payload
    after[table+slot*5:table+slot*5+5] = macro_entry(address, count, mode)
    key_at = base+control_offset(control)
    after[key_at] = MACRO_CODES[slot]
    # Payload first, then its descriptor, and the triggering key last.
    offsets = list(range(address, address+len(payload), 8))
    offsets += list(range((table+slot*5)&~7, ((table+slot*5+5+7)&~7), 8))
    offsets += [key_at & ~7]
    blocks = [(base, bytes(image[base:base+8]))]
    blocks += [(a, bytes(after[a:a+8])) for a in dict.fromkeys(offsets)]
    return bytes(after), blocks, slot


def restore_macro_blocks(before, after, base):
    """Restore only configuration assignments and the bounded macro region."""
    table = table_address(before, base)
    if table_address(after, base) != table:
        raise ValueError('Backup macro layout differs')
    allowed = set(range(table, EEPROM_SIZE-0x48))
    allowed |= set(range(base+KEYMAP_OFFSET, base+KEYMAP_OFFSET+160)) | {base+32}
    target = bytearray(before)
    for address in allowed:
        target[address] = after[address]
    changed = [a for a in range(0, EEPROM_SIZE, 8) if before[a:a+8] != target[a:a+8]]
    payload_start = (table+111)&~7
    ordered = [a for a in changed if a >= payload_start]
    ordered += [a for a in changed if table <= a < payload_start]
    ordered += [a for a in changed if base+KEYMAP_OFFSET <= a < base+KEYMAP_OFFSET+160]
    blocks = [(base, before[base:base+8])] + [(a, bytes(target[a:a+8])) for a in ordered]
    if before[base+32] != target[base+32]:
        blocks.append((base+32, bytes(target[base+32:base+33])))
    return bytes(target), blocks
