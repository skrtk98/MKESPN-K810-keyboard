"""Transport restricted to the K810 vendor configuration HID collection."""

from contextlib import contextmanager
import time

from .protocol import CONFIG_SIZE, EEPROM_SIZE, packet, validate_base, write_packets

SUPPORTED_IDS = {(0x30FA, 0x2350), (0x2130, 0x30FA)}


def enumerate_devices():
    import hid
    return [d for d in hid.enumerate()
            if (d["vendor_id"], d["product_id"]) in SUPPORTED_IDS
            and d["usage_page"] == 0xFF01 and d["usage"] == 1]


class Device:
    def __init__(self, info):
        import hid
        self.info = info
        self.hid = hid.device()
        self.hid.open_path(info["path"])

    def close(self):
        self.hid.close()

    def send(self, data):
        # This model's FeatureReportByteLength is 8 (confirmed via HidP_GetCaps).
        if len(data) != 8:
            raise ValueError("Expected an 8-byte feature report")
        count = self.hid.send_feature_report(data)
        if count != len(data):
            raise OSError(f"Short feature write: {count}/{len(data)}")

    def get(self, length=8):
        result = bytes(self.hid.get_feature_report(7, length))
        if len(result) != length or result[0] != 7:
            raise OSError(f"Invalid feature response: {result.hex(' ')}")
        return result

    def metadata(self):
        result = self.get(16)
        base = int.from_bytes(result[14:16], "little")
        validate_base(base)
        return base, result

    def read(self, address: int, length: int) -> bytes:
        if not 1 <= length <= 32 or not 0 <= address <= EEPROM_SIZE - length:
            raise ValueError("Read must be 1..32 bytes inside the EEPROM")
        # Mirrors 0x406fd0. Command 3 only stages data; no command 9 is sent.
        for i in range(length):
            self.send(packet(3, i, address, 0, length - 1))
        time.sleep(.001)
        self.send(packet(address=address))
        time.sleep(.001)
        result = bytearray()
        try:
            for i in range(length):
                self.send(packet(5, i, address, 0, length - 1))
                time.sleep(.001)
                result.append(self.get()[1])
        finally:
            time.sleep(.001)
            self.send(packet(1))
        return bytes(result)

    def read_range(self, address, length):
        return b"".join(self.read(a, min(8, address + length - a))
                        for a in range(address, address + length, 8))

    def snapshot(self):
        base, meta = self.metadata()
        data = self.read_range(base, CONFIG_SIZE)
        # A wrong interface or an unsupported firmware must not become a backup.
        if len(set(data)) < 3:
            raise ValueError("Configuration looks empty; refusing to use it")
        return base, meta, data

    def write_block(self, address, data):
        reports = write_packets(address, data)
        for report in reports[:-2]:
            self.send(report)
        time.sleep(.002)
        self.send(reports[-2])
        time.sleep(.010)
        self.send(reports[-1])

    def apply_blocks(self, base, blocks):
        # The vendor apply handler first enables configuration writes.
        self.send(bytes.fromhex("07 09 41 00 00 00 00 00"))
        time.sleep(.2)
        try:
            for offset, data in blocks:
                self.write_block(base + offset, data)
        finally:
            self.send(packet(0x11))
            time.sleep(.010)
            self.send(packet())


@contextmanager
def connect(path=None):
    matches = enumerate_devices()
    if path is not None:
        matches = [d for d in matches if d["path"].decode() == path]
    if len(matches) != 1:
        raise ValueError(f"Expected one K810 configuration interface, found {len(matches)}. Use list / --path.")
    device = Device(matches[0])
    try:
        yield device
    finally:
        device.close()
