import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mkespn_k810_keyboard.cli import load_backup
from mkespn_k810_keyboard.device import Device
from mkespn_k810_keyboard.protocol import (control_offset, keycode, packet, write_packets,
    CONFIG_SIZE, WHEEL_ACTIONS, WHEEL_OFFSET, wheel_action, set_wheel, changed_blocks)

VECTORS = json.loads(Path(__file__).with_name('vendor_vectors.json').read_text())
APPLY_VECTORS = json.loads(Path(__file__).with_name('vendor_apply_vectors.json').read_text())


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

    def close(self):
        self.closed = True


class ProtocolTests(unittest.TestCase):
    def test_original_apply_replays_control_block_before_wheel(self):
        self.assertEqual(APPLY_VECTORS['source_sha256'], VECTORS['source_sha256'])
        for mode, name in ((1, 'synthetic_apply'), (0, 'keys_mode_zero')):
            trace = APPLY_VECTORS[name]
            self.assertEqual(trace[0], {'set': '0709410000000000'})
            writes = [x for x in trace if 'write_address' in x]
            control = next(x for x in writes if x['write_address'] == 0xE0)
            wheel = next(x for x in writes if x['write_address'] == 0x100)
            self.assertEqual(len(bytes.fromhex(control['data'])), 8)
            self.assertEqual(bytes.fromhex(control['data'])[0] >> 7, mode)
            self.assertEqual(wheel['data'], '23')
            self.assertLess(writes.index(control), writes.index(wheel))

    @patch('mkespn_k810_keyboard.device.time.sleep')
    def test_close_exits_configuration_mode(self, sleep):
        device = object.__new__(Device); device.hid = FakeHid()
        device.send(packet(1))
        self.assertTrue(device.configuration_active)
        device.close()
        self.assertEqual(device.hid.trace[-3:], [
            {'set': '0718110000000000'}, {'set': '0718000000000000'}, {'set': '0720000000000000'}])
        self.assertEqual(device.hid.trace[-1], {'set': '0720000000000000'})
        self.assertFalse(device.configuration_active)
        self.assertTrue(device.hid.closed)
    def test_wheel_menu_matches_original_x86(self):
        values = list(WHEEL_ACTIONS.values())
        for entry in VECTORS['wheel_menu']:
            self.assertEqual(entry['code'], values[entry['choice']])

    def test_wheel_packing_matches_original_x86(self):
        names = {v: k for k, v in WHEEL_ACTIONS.items()}
        for entry in VECTORS['wheel_packing']:
            data = bytes(CONFIG_SIZE)
            data = set_wheel(set_wheel(data, 'up', names[entry['up']]), 'down', names[entry['down']])
            self.assertEqual(bytes(data[WHEEL_OFFSET:WHEEL_OFFSET+1]).hex(), entry['data'])
            self.assertEqual(entry['address'], 0xE0 + WHEEL_OFFSET)
            self.assertEqual(wheel_action(data, 'up'), names[entry['up']])
            self.assertEqual(wheel_action(data, 'down'), names[entry['down']])

    def test_wheel_single_byte_write_matches_original_x86(self):
        self.assertEqual([{'set': b.hex()} for b in write_packets(0x100, b'\x23')], VECTORS['wheel_write'])

    def test_wheel_change_preserves_other_nibble_and_configuration(self):
        before = bytes([0x10] * CONFIG_SIZE)
        for direction in ('up', 'down'):
            for action in WHEEL_ACTIONS:
                after = set_wheel(before, direction, action)
                opposite = 'down' if direction == 'up' else 'up'
                self.assertEqual(wheel_action(after, opposite), wheel_action(before, opposite))
                self.assertEqual(after[:WHEEL_OFFSET], before[:WHEEL_OFFSET])
                self.assertEqual(after[WHEEL_OFFSET+1:], before[WHEEL_OFFSET+1:])
                blocks = changed_blocks(before, after)
                if blocks:
                    self.assertEqual(blocks[0], (0, before[:8]))
                    self.assertTrue(all(o == WHEEL_OFFSET and len(b) == 1 for o, b in blocks[1:]))
        with self.assertRaises(ValueError): set_wheel(before, 'up', 'f13')
        after = bytearray(before); after[0] ^= 1
        with self.assertRaises(ValueError): changed_blocks(before, after)

    def test_writes_replay_unchanged_control_block_and_noop_does_not_write(self):
        before = bytes([0xC0, 0xF0, 0x1F, 0x0F, 0x1F, 0xFF, 0, 0xF0]) + bytes(CONFIG_SIZE-8)
        self.assertEqual(changed_blocks(before, before), [])
        after = set_wheel(before, 'up', 'scroll-up')
        self.assertEqual(changed_blocks(before, after), [(0, before[:8]), (WHEEL_OFFSET, b'\x20')])
        after = bytearray(before); after[control_offset('kp1')] = 104
        self.assertEqual(changed_blocks(before, after)[0], (0, before[:8]))
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
