"""Single-key firmware actions, decoded from 0x4080e0 and UniqueName labels."""
ACTIONS = {
    'play-pause': 0xC9, 'volume-down': 0xCA, 'volume-up': 0xCB,
    'next-track': 0xCC, 'previous-track': 0xCD, 'media-player': 0xCE,
    'mail': 0xCF, 'browser-forward': 0xD0, 'browser-stop': 0xD1,
    'browser-back': 0xD2, 'browser-refresh': 0xD3, 'browser-search': 0xD4,
    'browser-favorites': 0xD5, 'mute': 0xD6, 'my-computer': 0xD7,
    'media-stop': 0xD8, 'calculator': 0xD9, 'browser-home': 0xDA,
    'led-color': 0xE8, 'led-mode': 0xE9, 'led-brightness-up': 0xEA,
    'led-brightness-down': 0xEB, 'led-speed-up': 0xEC,
    'led-speed-down': 0xED, 'led-toggle': 0xF0,
}
