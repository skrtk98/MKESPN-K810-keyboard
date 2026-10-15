"""K201 protocol decoded from Gaming Keyboard.exe; see docs/PROTOCOL.md."""

from .actions import ACTIONS

REPORT_ID = 7
EEPROM_SIZE = 8192
CONFIG_SIZE = 0xF8
KEYMAP_OFFSET = 0x48
WHEEL_OFFSET = 0x20
# Original menu 0x420d00: items 98..105 map to these firmware values.
WHEEL_ACTIONS = {
    "volume-up": 0, "volume-down": 1, "scroll-up": 2, "scroll-down": 3,
    "led-speed-up": 7, "led-speed-down": 8,
    "led-brightness-up": 9, "led-brightness-down": 10,
}


def wheel_action(data: bytes, direction: str) -> str:
    if direction not in ("up", "down"):
        raise ValueError("Wheel direction must be up or down")
    code = (data[WHEEL_OFFSET] >> (4 if direction == "up" else 0)) & 15
    return next((name for name, value in WHEEL_ACTIONS.items() if value == code), f"unknown-0x{code:x}")


def set_wheel(data: bytes, direction: str, action: str) -> bytearray:
    if direction not in ("up", "down") or action not in WHEEL_ACTIONS:
        raise ValueError("Unsupported wheel direction or action")
    after = bytearray(data)
    shift = 4 if direction == "up" else 0
    after[WHEEL_OFFSET] = (after[WHEEL_OFFSET] & (0x0F if shift else 0xF0)) | (WHEEL_ACTIONS[action] << shift)
    return after


def changed_blocks(before: bytes, after: bytes) -> list[tuple[int, bytes]]:
    """Plan edits plus the unchanged control block required to activate them."""
    if len(before) != CONFIG_SIZE or len(after) != CONFIG_SIZE:
        raise ValueError("Invalid configuration length")
    allowed = set(range(KEYMAP_OFFSET, KEYMAP_OFFSET + 160)) | {WHEEL_OFFSET}
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(before, after))):
        raise ValueError("Attempt to modify an unsupported configuration field")
    blocks = [(o, bytes(after[o:o + 8])) for o in range(KEYMAP_OFFSET, KEYMAP_OFFSET + 160, 8)
              if before[o:o + 8] != after[o:o + 8]]
    if before[WHEEL_OFFSET] != after[WHEEL_OFFSET]:
        blocks.append((WHEEL_OFFSET, bytes(after[WHEEL_OFFSET:WHEEL_OFFSET + 1])))
    # The vendor Apply handler rewrites this block after 07/09/41. Omitting it
    # leaves stored assignments readable but inactive until a physical mode change.
    # Never take these bytes from an imported/tampered draft.
    return [(0, bytes(before[:8])), *blocks] if blocks else []

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
    if name in ACTIONS:
        return ACTIONS[name]
    try:
        value = int(name, 0)
    except ValueError:
        raise ValueError(f"Unknown key: {name}. Use a..z, f1..f24, kp0..kp9 or 0xNN.") from None
    if not (0 <= value <= 0xA4 or 0xE0 <= value <= 0xE7 or value in ACTIONS.values()):
        raise ValueError("Only ordinary keyboard usages 0x00..0xA4 and modifiers 0xE0..0xE7 are supported.")
    return value


def keyname(code: int) -> str:
    if code in ACTIONS.values():
        return next(k for k, v in ACTIONS.items() if v == code)
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
