"""K201 protocol decoded from Gaming Keyboard.exe; see docs/PROTOCOL.md."""

REPORT_ID = 7
EEPROM_SIZE = 8192
CONFIG_SIZE = 0xF8
KEYMAP_OFFSET = 0x48

# Names describe the factory function, not an assumed physical row/column.
CONTROLS = {
    "kp1": (0, 89), "kp2": (1, 90), "kp3": (2, 91),
    "kp4": (3, 92), "kp5": (4, 93), "kp6": (5, 94),
    "kp7": (6, 95), "kp8": (7, 96), "enter": (8, 40),
    "tab": (9, 43), "kp9": (10, 97), "kp0": (11, 98),
    "left": (12, 80), "right": (13, 79), "down": (14, 81), "up": (15, 82),
}
KEYS = {chr(97 + i): 4 + i for i in range(26)}
KEYS.update({str(i): 29 + i for i in range(1, 10)})
KEYS.update({"0": 39, "enter": 40, "escape": 41, "backspace": 42,
             "tab": 43, "space": 44, "delete": 76, "right": 79,
             "left": 80, "down": 81, "up": 82, "none": 0})
KEYS.update({f"f{i}": 57 + i for i in range(1, 13)})
KEYS.update({f"f{i}": 91 + i for i in range(13, 25)})
KEYS.update({f"kp{i}": 88 + i for i in range(1, 10)})
KEYS.update({"kp0": 98, "kp_decimal": 99, "kp_enter": 88,
             "left_ctrl": 224, "left_shift": 225, "left_alt": 226,
             "left_gui": 227, "right_ctrl": 228, "right_shift": 229,
             "right_alt": 230, "right_gui": 231})


def keycode(name: str) -> int:
    name = name.lower()
    if name in KEYS:
        return KEYS[name]
    try:
        value = int(name, 0)
    except ValueError:
        raise ValueError(f"Unknown key: {name}. Use a..z, f1..f24, kp0..kp9 or 0xNN.") from None
    if not (0 <= value <= 0xA4 or 0xE0 <= value <= 0xE7):
        raise ValueError("Only ordinary keyboard usages 0x00..0xA4 and modifiers 0xE0..0xE7 are supported.")
    return value


def keyname(code: int) -> str:
    return next((k for k, v in KEYS.items() if v == code), f"0x{code:02x}")


def packet(command=0, index=0, address=0, value=0, last=0) -> bytes:
    if not (0 <= address < EEPROM_SIZE):
        raise ValueError("EEPROM address out of range")
    return bytes((7, 0x18, command, index, address & 255, address >> 8, value, last))


def write_packets(address: int, data: bytes) -> list[bytes]:
    if not 1 <= len(data) <= 32 or address + len(data) > EEPROM_SIZE:
        raise ValueError("Write must be 1..32 bytes inside the EEPROM")
    result = [packet(3, i, address, b, len(data) - 1) for i, b in enumerate(data)]
    result.extend((packet(9, address=address, last=len(data) - 1), packet(1, address=address)))
    return result


def control_offset(control: str) -> int:
    return KEYMAP_OFFSET + CONTROLS[control][0] * 8


def validate_base(base: int) -> None:
    if base < 0xD8 or base % 8 or base + CONFIG_SIZE > EEPROM_SIZE:
        raise ValueError(f"Unexpected configuration base: 0x{base:04x}")
