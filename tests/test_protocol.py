import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mkespn_k810_keyboard.cli import load_backup
from mkespn_k810_keyboard.device import Device
from mkespn_k810_keyboard.protocol import control_offset, keycode, packet, write_packets

VECTORS = json.loads(Path(__file__).with_name('vendor_vectors.json').read_text())


class FakeHid:
    def __init__(self):
        self.trace = []
        self.index = 0

    def send_feature_report(self, data):
        self.trace.append({"set": data.hex()})
        return len(data)

    def get_feature_report(self, report_id, length):
        self.trace.append({"get": length})
        value = bytes.fromhex(VECTORS['data'])[self.index]
        self.index += 1
        return [report_id, value] + [0] * (length - 2)


class ProtocolTests(unittest.TestCase):
    def test_write_matches_original_x86(self):
        actual = [{"set": b.hex()} for b in write_packets(VECTORS['address'], bytes.fromhex(VECTORS['data']))]
        self.assertEqual(VECTORS['write'], actual)

    @patch('mkespn_k810_keyboard.device.time.sleep')
    def test_read_matches_original_x86(self, sleep):
        device = object.__new__(Device)
        device.hid = FakeHid()
        result = device.read(VECTORS['address'], 8)
        self.assertEqual(result.hex(), VECTORS['data'])
        self.assertEqual(device.hid.trace, VECTORS['read'])
        self.assertFalse(any(bytes.fromhex(r['set'])[2] == 9 for r in device.hid.trace if 'set' in r))

    def test_key_positions_match_original_table_serializer(self):
        for column, block in enumerate(VECTORS['table']):
            self.assertEqual(block['address'], 0x128 + column * 8)
            self.assertEqual(bytes.fromhex(block['data']), bytes(column + row * 20 for row in range(8)))
        self.assertEqual(control_offset('kp1'), 0x48)
        self.assertEqual(control_offset('up'), 0x48 + 15 * 8)

    def test_keycodes_and_bounds(self):
        self.assertEqual(keycode('f13'), 0x68)
        self.assertEqual(keycode('f24'), 0x73)
        self.assertEqual(keycode('9'), 0x26)
        for value in ('ctrl+c', '256', '-1', '0xf4'):
            with self.assertRaises(ValueError):
                keycode(value)
        for address, data in ((8192, b'\0'), (8191, b'\0\0'), (0, b''), (0, bytes(33))):
            with self.assertRaises(ValueError):
                write_packets(address, data)
        with self.assertRaises(ValueError):
            packet(address=-1)

    def test_backup_checksum_detects_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'backup.json'
            data = bytes(248)
            doc = {"format": "mkespn-k810-config-v1", "base": 0xe0,
                   "data_hex": data.hex(), "sha256": hashlib.sha256(data).hexdigest()}
            path.write_text(json.dumps(doc))
            self.assertEqual(load_backup(path)[1], data)
            doc['data_hex'] = (b'\x01' + data[1:]).hex()
            path.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                load_backup(path)


if __name__ == '__main__':
    unittest.main()
