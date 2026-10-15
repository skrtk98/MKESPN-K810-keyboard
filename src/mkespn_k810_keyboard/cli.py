import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from .device import connect, enumerate_devices
from .actions import ACTIONS
from .macros import plan_macro, restore_macro_blocks, MACRO_CODES
from .lighting import decode_lighting, set_lighting, lighting_blocks
from .protocol import (CONFIG_SIZE, CONTROLS, KEYMAP_OFFSET, control_offset,
                       keycode, keyname, validate_base, write_packets,
                       WHEEL_ACTIONS, WHEEL_OFFSET, wheel_action, set_wheel, changed_blocks)


def save_backup(device, base, meta, data, output=None, image=None):
    if image is not None and (len(image) != 8192 or image[base:base+CONFIG_SIZE] != data):
        raise ValueError('EEPROM backup and configuration disagree')
    if output is None:
        output = Path("backups") / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "mkespn-k810-config-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "vendor_id": device.info["vendor_id"], "product_id": device.info["product_id"],
        "base": base, "metadata_hex": meta.hex(), "data_hex": data.hex(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    if image is not None:
        payload['eeprom_hex'] = image.hex()
        payload['eeprom_sha256'] = hashlib.sha256(image).hexdigest()
    # Never replace an existing backup by accident.
    with output.open("x", encoding="utf8") as stream:
        json.dump(payload, stream, indent=2)
    return output


def load_backup(path):
    doc = json.loads(Path(path).read_text(encoding="utf8"))
    if doc["format"] != "mkespn-k810-config-v1":
        raise ValueError("Unsupported backup format")
    data = bytes.fromhex(doc["data_hex"])
    validate_base(doc["base"])
    if len(data) != CONFIG_SIZE or hashlib.sha256(data).hexdigest() != doc["sha256"]:
        raise ValueError("Backup size or checksum mismatch")
    if 'eeprom_hex' in doc:
        image = bytes.fromhex(doc['eeprom_hex'])
        if len(image) != 8192 or hashlib.sha256(image).hexdigest() != doc['eeprom_sha256']:
            raise ValueError('Full EEPROM backup checksum mismatch')
        if image[doc['base']:doc['base']+CONFIG_SIZE] != data:
            raise ValueError('EEPROM backup and configuration disagree')
    return doc, data


def print_map(data):
    for control in CONTROLS:
        value = data[control_offset(control)]
        print(f"{control:>6}: {keyname(value):<14} (0x{value:02x})")
    for direction in ("up", "down"):
        print(f"wheel-{direction}: {wheel_action(data, direction)}")
    print(f"wheel byte: 0x{data[WHEEL_OFFSET]:02x} (directions follow manufacturer naming)")


def perform_change(device, base, meta, before, after, apply):
    blocks = changed_blocks(before, after)
    if not blocks:
        print("No changes.")
        return
    for offset, block in blocks:
        print(f"0x{base + offset:04x}: {before[offset:offset + len(block)].hex(' ')} -> {block.hex(' ')}")
        for report in write_packets(base + offset, block):
            print(f"  SET_FEATURE {report.hex(' ')}")
    if not apply:
        print("Preview only. Add --apply to write. The read requests do not commit EEPROM changes.")
        return
    backup = save_backup(device, base, meta, before)
    print(f"Backup: {backup.resolve()}")
    if device.read_range(base, CONFIG_SIZE) != before:
        raise OSError("Device configuration changed since snapshot; refusing to overwrite it")
    device.apply_blocks(base, blocks)
    actual = device.read_range(base, CONFIG_SIZE)
    if actual != bytes(after):
        raise OSError(f"Read-back verification failed. Original configuration: {backup.resolve()}")
    print("Written and verified. Unplug/replug to check persistence.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="MKESPN K810 independent HID configurator")
    parser.add_argument("--path", help="Exact configuration HID path from list")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="Enumerate configuration interfaces without sending reports")
    sub.add_parser('actions', help='List media and lighting action names without USB access')
    sub.add_parser("info", help="Read device metadata")
    sub.add_parser("show", help="Read the current key assignments")
    sub.add_parser('light', help='Read Light-tab fields')
    light=sub.add_parser('set-light', help='Set Light-tab fields from a JSON object')
    light.add_argument('file')
    light.add_argument('--apply',action='store_true')
    backup = sub.add_parser("backup", help="Save the 248-byte configuration region (not all EEPROM)")
    backup.add_argument("output", nargs="?")
    backup.add_argument('--full', action='store_true', help='Include EEPROM macro storage')
    assign = sub.add_parser("set-key", help="Remap a key or a joystick direction")
    assign.add_argument("control", choices=CONTROLS)
    assign.add_argument("key", type=keycode)
    assign.add_argument("--apply", action="store_true")
    wheel = sub.add_parser("set-wheel", help="Assign a manufacturer wheel action to one direction")
    wheel.add_argument("direction", choices=("up", "down"))
    wheel.add_argument("action", choices=WHEEL_ACTIONS)
    wheel.add_argument("--apply", action="store_true")
    restore = sub.add_parser("restore", help="Restore only the keymap from a backup")
    restore.add_argument("backup")
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--include-wheel", action="store_true", help="Also restore the wheel byte")
    restore.add_argument('--include-macros', action='store_true', help='Restore assignments and macro storage from a full backup')
    macro = sub.add_parser('set-macro', help='Assign a JSON macro containing key/mouse events')
    macro.add_argument('control', choices=CONTROLS)
    macro.add_argument('file')
    macro.add_argument('--apply', action='store_true')
    macros = sub.add_parser('set-macros', help='Assign a JSON object mapping control names to macros')
    macros.add_argument('file')
    macros.add_argument('--apply', action='store_true')
    shortcut = sub.add_parser('shortcut', help='Assign simultaneous keys, e.g. left_ctrl c')
    shortcut.add_argument('control', choices=CONTROLS)
    shortcut.add_argument('keys', nargs='+')
    shortcut.add_argument('--apply', action='store_true')
    mouse = sub.add_parser('mouse', help='Assign mouse click or wheel using an onboard macro')
    mouse.add_argument('control', choices=CONTROLS)
    mouse.add_argument('action', choices=['left','right','middle','scroll-up','scroll-down'])
    mouse.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'actions':
            for name, code in ACTIONS.items():
                print(f'{name:24} 0x{code:02x}')
            return
        if args.command == "list":
            result = enumerate_devices()
            print(json.dumps(result, indent=2, ensure_ascii=False,
                             default=lambda v: v.decode() if isinstance(v, bytes) else str(v)))
            return
        with connect(args.path) as device:
            if args.command == "info":
                base, meta = device.metadata()
                print(f"USB {device.info['vendor_id']:04x}:{device.info['product_id']:04x}")
                print(f"Configuration base: 0x{base:04x}")
                print(f"Metadata: {meta.hex(' ')}")
                return
            base, meta, before = device.snapshot()
            if args.command == "show":
                print_map(before)
            elif args.command == 'light':
                print(json.dumps(decode_lighting(before),indent=2))
            elif args.command == 'set-light':
                after=set_lighting(before,json.loads(Path(args.file).read_text(encoding='utf8')))
                blocks=lighting_blocks(before,after)
                for at,block in blocks:print(f'0x{base+at:04x}: {before[at:at+8].hex(" ")} -> {block.hex(" ")}')
                if not blocks:
                    print('No changes.');return
                if not args.apply:
                    print('Preview only. Add --apply to write.');return
                recovery=save_backup(device,base,meta,before)
                print(f'Backup: {recovery.resolve()}',flush=True)
                if device.read_range(base,CONFIG_SIZE)!=before:
                    raise ValueError('Configuration changed before lighting write')
                device.apply_blocks(base,blocks)
                if device.read_range(base,CONFIG_SIZE)!=after:
                    raise OSError(f'Lighting read-back mismatch. Backup: {recovery.resolve()}')
                print('Lighting written and verified across all 248 configuration bytes.')
            elif args.command == "backup":
                image = device.read_range(0, 8192) if args.full else None
                print(save_backup(device, base, meta, before, args.output, image=image).resolve())
            elif args.command in ('set-macro', 'set-macros', 'shortcut', 'mouse') or (args.command == 'restore' and args.include_macros):
                print('Reading complete EEPROM (8192 bytes)...', flush=True)
                image = device.read_range(0, 8192)
                if image[base:base+CONFIG_SIZE] != before:
                    raise ValueError('Device changed while reading EEPROM; retry')
                if args.command == 'restore':
                    doc, saved = load_backup(args.backup)
                    if doc['base'] != base or (doc['vendor_id'], doc['product_id']) != (device.info['vendor_id'], device.info['product_id']):
                        raise ValueError('Backup device layout does not match')
                    if 'eeprom_hex' not in doc:
                        raise ValueError('Macro restoration needs a --full backup')
                    target, absolute = restore_macro_blocks(image, bytes.fromhex(doc['eeprom_hex']), base)
                elif args.command == 'set-macros':
                    specs=json.loads(Path(args.file).read_text(encoding='utf8'))
                    if not isinstance(specs,dict) or not specs or set(specs)-set(CONTROLS):
                        raise ValueError('Expected an object mapping supported controls to macros')
                    target=image
                    for control,spec in specs.items():
                        target,_,slot=plan_macro(target,base,control,spec)
                        print(f'{control}: macro slot {slot+1}')
                    target,absolute=restore_macro_blocks(image,target,base)
                else:
                    if args.command == 'set-macro':
                        spec = json.loads(Path(args.file).read_text(encoding='utf8'))
                    elif args.command == 'shortcut':
                        spec = {'events': [{'type':'key-down','key':k} for k in args.keys] +
                                          [{'type':'key-up','key':k} for k in reversed(args.keys)]}
                    elif args.action.startswith('scroll-'):
                        spec = {'events':[{'type':'scroll','steps':1 if args.action=='scroll-up' else -1}]}
                    else:
                        spec = {'events':[{'type':'mouse-down','button':args.action}, {'type':'mouse-up','button':args.action}]}
                    target, absolute, slot = plan_macro(image, base, args.control, spec)
                    print(f'Macro slot {slot+1}')
                for address, block in absolute:
                    print(f'0x{address:04x}: {image[address:address+len(block)].hex(" ")} -> {block.hex(" ")}')
                if not args.apply:
                    print('Preview only. Add --apply to write.')
                    return
                recovery = save_backup(device, base, meta, before, image=image)
                print(f'Full backup: {recovery.resolve()}')
                if device.read_range(base, CONFIG_SIZE) != before:
                    raise ValueError('Configuration changed before write; refusing to overwrite')
                for address, block in absolute:
                    if device.read_range(address,len(block)) != image[address:address+len(block)]:
                        raise ValueError('Write target changed before write; refusing to overwrite')
                device.apply_blocks(base, [(a-base,b) for a,b in absolute])
                print('Verifying complete EEPROM...', flush=True)
                if device.read_range(0,8192) != target:
                    raise OSError(f'Macro read-back mismatch. Full backup: {recovery.resolve()}')
                print('Written and verified across all 8192 EEPROM bytes.')
            else:
                after = bytearray(before)
                if args.command == "set-key":
                    after[control_offset(args.control)] = args.key
                elif args.command == "set-wheel":
                    after = set_wheel(before, args.direction, args.action)
                else:
                    doc, saved = load_backup(args.backup)
                    if (doc['base'], doc['vendor_id'], doc['product_id']) != (
                            base, device.info['vendor_id'], device.info['product_id']):
                        raise ValueError("Backup device ID or configuration base does not match")
                    after[KEYMAP_OFFSET:KEYMAP_OFFSET + 160] = saved[KEYMAP_OFFSET:KEYMAP_OFFSET + 160]
                    if any(a != b and b in MACRO_CODES for a,b in zip(before[KEYMAP_OFFSET:KEYMAP_OFFSET+160], saved[KEYMAP_OFFSET:KEYMAP_OFFSET+160])):
                        raise ValueError('Macro assignments need a full backup and --include-macros')
                    if args.include_wheel:
                        if any(wheel_action(saved, d).startswith("unknown-") for d in ("up", "down")):
                            raise ValueError("Backup contains unsupported wheel action values")
                        after[WHEEL_OFFSET] = saved[WHEEL_OFFSET]
                perform_change(device, base, meta, before, after, args.apply)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
