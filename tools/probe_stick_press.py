"""Temporary hidden-column probe; not a supported user-facing assignment.

Only columns 16/17 are accepted. Back up the configuration, preserve all other
bytes, verify the write, and use `restore BACKUP` after the physical test.
"""
import argparse
import json

from mkespn_k810_keyboard.cli import load_backup, save_backup
from mkespn_k810_keyboard.device import connect
from mkespn_k810_keyboard.protocol import changed_blocks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    probe = sub.add_parser('probe')
    probe.add_argument('column', type=int, choices=(16, 17))
    probe.add_argument('--apply', action='store_true')
    restore = sub.add_parser('restore')
    restore.add_argument('backup')
    args = parser.parse_args()
    with connect() as device:
        base, meta, before = device.snapshot()
        after = bytearray(before)
        if args.command == 'probe':
            offset = 0x48 + args.column * 8
            after[offset] = 0x6E  # Keyboard F19, separate from prior test macros.
            if not args.apply:
                print(json.dumps({'offset': offset, 'address': base + offset,
                                  'before': before[offset], 'after': after[offset]}))
                return
            backup = save_backup(device, base, meta, before)
            print(f'BACKUP={backup.resolve()}', flush=True)
        else:
            doc, original = load_backup(args.backup)
            if doc['base'] != base:
                raise ValueError('Configuration base changed')
            differences = [i for i, (a, b) in enumerate(zip(before, original)) if a != b]
            if any(not ((i in (0xC8, 0xD0) and before[i] == 0x6E)
                        or (i == 0 and before[i] ^ original[i] == 0x80))
                   for i in differences):
                raise ValueError('Unexpected concurrent edit; refusing restoration')
            after[:] = original
        if device.read_range(base, len(before)) != before:
            raise ValueError('Concurrent device edit')
        # A physical mode switch changes header bit 7. Restore it explicitly;
        # changed_blocks deliberately replays the current header for normal edits.
        if args.command == 'restore':
            table_after = bytearray(after)
            table_after[:8] = before[:8]
            blocks = [(0, bytes(after[:8])),
                      *[(o, data) for o, data in changed_blocks(before, table_after) if o]]
        else:
            blocks = changed_blocks(before, after)
        device.apply_blocks(base, blocks)
        if device.read_range(base, len(before)) != after:
            raise OSError('Read-back mismatch; retain backup for recovery')
        print('Written and verified; closing configuration transport.', flush=True)


if __name__ == '__main__':
    main()
