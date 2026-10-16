"""Compare known vendor initialization/capture states; no EEPROM block writes.

Start the FF00 and standard-input observers first. This controller enters the
vendor startup state, then waits for command.txt containing 'capture' or 'finish'.
Always replays the original runtime flag command and verifies the 248-byte snapshot.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from mkespn_k810_keyboard.cli import save_backup
from mkespn_k810_keyboard.device import connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=540)
    parser.add_argument('--control-bit7-before-capture', action='store_true',
                        help='Try known 09/flags bit 7; this alone did not activate custom keys')
    args = parser.parse_args()
    if not 10 <= args.timeout <= 540:
        raise ValueError('Timeout must be 10..540 seconds')
    root = args.run_dir
    root.mkdir(parents=True, exist_ok=True)
    status_path = root / 'status.json'
    command_path = root / 'command.txt'
    if status_path.exists() or command_path.exists():
        raise ValueError('Refusing to reuse controller state')
    result = dict(started_utc=datetime.now(timezone.utc).isoformat(), commands=[], phase='snapshot')

    def save():
        status_path.write_text(json.dumps(result, indent=2), encoding='utf8')

    with connect() as device:
        base, meta, before = device.snapshot()
        backup = save_backup(device, base, meta, before)
        result.update(backup=str(backup.resolve()), base=base, header=before[:8].hex())
        device.finish_configuration()

        def send(packet):
            device.send(bytes.fromhex(packet))
            result['commands'].append(dict(utc=datetime.now(timezone.utc).isoformat(), report=packet))
            save()

        try:
            send('07 18 11 00 00 00 00 00')
            time.sleep(.010)
            send('07 18 00 00 00 00 00 00')
            if args.control_bit7_before_capture:
                send(f'07 09 {(before[0] | 0x80) & 0xD5:02x} 00 00 00 00 00')
                result['control_bit7_before_capture'] = True
            result['phase'] = 'initialized'
            save()
            print('READY: vendor initialization complete; awaiting physical input.', flush=True)
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                command = command_path.read_text(encoding='utf8').strip() if command_path.exists() else ''
                if command == 'finish':
                    break
                if command == 'capture' and result['phase'] == 'initialized':
                    send('07 09 40 00 00 00 00 00')
                    result['phase'] = 'capture'
                    save()
                    print('READY: vendor key-assignment state 09/40; awaiting physical input.', flush=True)
                elif command not in ('', 'capture'):
                    raise ValueError('Unknown controller command')
                time.sleep(.1)
            else:
                result['timed_out'] = True
        finally:
            # Original 428270..4282BD packs header bits 7,6,4,2,0 into 09/flags.
            # This restores runtime mode without an EEPROM block-write sequence.
            try:
                send(f'07 09 {before[0] & 0xD5:02x} 00 00 00 00 00')
            finally:
                device.finish_configuration()
            _, _, after = device.snapshot()
            device.finish_configuration()
            result['differences'] = [dict(offset=hex(i), before=a, after=b)
                                     for i, (a, b) in enumerate(zip(before, after)) if a != b]
            result['verified'] = before == after
            result['phase'] = 'finished'
            save()
            if before != after:
                raise OSError(f'Configuration mismatch; retain backup {backup}')
            print('Finished: original flag command replayed; full 248-byte configuration unchanged.', flush=True)


if __name__ == '__main__':
    main()
