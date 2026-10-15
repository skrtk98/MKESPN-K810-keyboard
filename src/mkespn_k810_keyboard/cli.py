import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from .device import connect, enumerate_devices
from .protocol import (CONFIG_SIZE, CONTROLS, KEYMAP_OFFSET, control_offset,
                       keycode, keyname, validate_base, write_packets,
                       WHEEL_ACTIONS, WHEEL_OFFSET, wheel_action, set_wheel, changed_blocks)


def save_backup(device, base, meta, data, output=None):
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
    sub.add_parser("info", help="Read device metadata")
    sub.add_parser("show", help="Read the current key assignments")
    backup = sub.add_parser("backup", help="Save the 248-byte configuration region (not all EEPROM)")
    backup.add_argument("output", nargs="?")
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
    args = parser.parse_args(argv)
    try:
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
            elif args.command == "backup":
                print(save_backup(device, base, meta, before, args.output).resolve())
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
                    if args.include_wheel:
                        if any(wheel_action(saved, d).startswith("unknown-") for d in ("up", "down")):
                            raise ValueError("Backup contains unsupported wheel action values")
                        after[WHEEL_OFFSET] = saved[WHEEL_OFFSET]
                perform_change(device, base, meta, before, after, args.apply)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
