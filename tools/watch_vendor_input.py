"""Observe only the K810 FF00/1 input collection. Sends no HID reports."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import hid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        raise ValueError('Duration must be 1..600 seconds')
    matches = [d for d in hid.enumerate(0x30FA, 0x2350)
               if d['usage_page'] == 0xFF00 and d['usage'] == 1]
    if len(matches) != 1:
        raise ValueError(f'Expected one K810 FF00/1 collection, found {len(matches)}')
    device = hid.device()
    events = []
    started = time.monotonic()
    result = dict(started_utc=datetime.now(timezone.utc).isoformat(),
                  usage_page=0xFF00, usage=1, report_id=6, sends=0, events=events)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf8')

    try:
        device.open_path(matches[0]['path'])
        print('READY: reading K810 FF00/1 report 6; no commands sent.', flush=True)
        checkpoint = started
        while time.monotonic() - started < args.seconds:
            if args.stop_file and args.stop_file.exists():
                break
            data = device.read(3, 50)
            if data:
                event = dict(seconds=round(time.monotonic() - started, 3),
                             data_hex=bytes(data).hex())
                events.append(event)
                print(json.dumps(event), flush=True)
            if time.monotonic() - checkpoint >= 1:
                save()
                checkpoint = time.monotonic()
    finally:
        device.close()
        save()
        print(f'Saved {len(events)} vendor input reports.', flush=True)


if __name__ == '__main__':
    main()
