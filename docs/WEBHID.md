# WebHID static application

## Architecture

`web/` is buildless HTML/CSS and native JavaScript modules. GitHub Pages hosts
only that directory. All HID communication, hashing and backup processing happen
locally. No server, backend bridge, WebUSB driver replacement, external font,
CDN runtime, telemetry or browser extension is required for users.

WebHID requires a secure context and user permission. Desktop Chrome/Edge are
the primary target. Firefox/Safari/iOS and ordinary Android browsers do not offer
this API. A responsive, explicitly isolated demo works without HID support.
The application does not claim compatibility with every browser or USB host.

References:
- [Chrome WebHID documentation](https://developer.chrome.com/docs/capabilities/hid)
- [WebHID specification](https://hid.spec.whatwg.org/)
- [MDN browser compatibility source](https://github.com/mdn/browser-compat-data/blob/main/api/HID.json)
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

## Adapting the protocol

Python's 16-byte `GET_FEATURE` is not directly expressible in WebHID:
`receiveFeatureReport(7)` has no length argument. The actual report descriptor
declares seven payload bytes plus the ID. We instead read eight bytes at EEPROM
address `0x00D0` using the original app's ordinary byte-read sequence:

```text
e1 1e e0 00 f0 0f 00 00
      -----
      configuration base (LE) = 0x00E0
```

The original app writes that structure at `0x41035B..0x410383`.
Both magic words and address bounds/alignment must pass before configuration
reads or writes proceed. There is no guessed/default address fallback.

`sendFeatureReport(7, packet.slice(1))` sends seven bytes; the report ID is a
separate argument. Feature responses preserve the operating system's report ID
as described by the specification. This implementation accepts the observed
eight-byte form starting with ID 7 and rejects other formats.

Only `30FA:2350`, UsagePage `FF01`, Usage 1 with Feature Report 7 is offered.

The separate vendor input collection (`FF00/1`, Input Report 6, two payload
bytes) can be opened natively. In the 2026-10-16 parallel hardware test it
produced zero reports while the K810's standard collections produced 47 input
events. No physical-input notification enable command has been identified in
the vendor software. This is distinct from browser protection of standard
keyboard/mouse collections; see [RAW_HID.md](RAW_HID.md).
The previously observed `2130:30FA` variant remains unsupported in the Web UI.
Chrome's protected keyboard input reports are not requested; the vendor
configuration collection is separately accessible.

## Write boundaries and recovery

- Ordinary UI edits affect the 16 exposed control bytes and the wheel assignment
  byte at configuration offset `0x20`. Macro saves also write the descriptor table
  and payload region. Full-backup restoration restores the 160-byte key table,
  wheel byte and macro region; RGB, mode and reserved regions remain unchanged.
- Each changed column is written as its original 8-byte block with the other
  seven bytes preserved. The wheel's two nibbles are combined into one single-byte
  write, preserving the opposite direction when only one changes. RGB settings,
  wheel matrix columns and configuration headers cannot be edited by ordinary
  key edits. Macro writes have a separate byte-level boundary guard.
- Every nonempty save first replays the current eight-byte control block at
  `base + 0`, even though its bytes are unchanged. The original Apply handler
  writes this block after `07 09 41`. Omitting it left the saved wheel assignments
  inactive in hardware testing. Drafts/imports cannot alter these control bytes.
- Before writing, read the configuration again and compare with the session
  snapshot; concurrent changes cause an abort.
- Web Locks serialize USB operations between same-origin tabs. Close other
  configurators; locks cannot coordinate with native programs or other origins.
- Save a SHA-256 checked backup to localStorage **before** EEPROM commits. If
  storage is unavailable/full, abort. One latest recovery backup is kept.
- Read back and compare the complete 248-byte region after ordinary writes.
  Macro saves and full-backup restoration first capture all 8,192 EEPROM bytes,
  save recovery data, check every proposed write block again, and verify the
  entire EEPROM afterward. This takes several minutes over the byte-read protocol.
- After reads and writes, send the original application's full configuration
  finalization (`07 18 11`, wait 10ms, `07 18 00`, `07 20`, wait 10ms).
  The block-local `18 01` alone did not reliably resume physical input in testing.
- A failure requires rereading the device before further edits are saved.
- Backups are compatible with the Python `mkespn-k810-config-v1` format. The Web
  backup has an empty `metadata_hex` and an additional `header_hex`, since the
  variable-length native metadata request is unavailable.
  Optional `eeprom_hex` and `eeprom_sha256` fields carry a full EEPROM snapshot.
  Imports are limited to 64 KiB and both hashes and configuration consistency
  are checked. Legacy backups cannot restore new macro references without payloads.
- Browser storage belongs to the HTTPS origin and may be removed by the browser.
  Download backups for durable recovery. Same-model devices have no useful
  serial number, so users must keep backups associated with the original unit.

The page includes a same-origin CSP, disables network connections, and loads
all runtime assets locally. This is not an audit of all software distributed by
the hardware manufacturer.

## Design system

The official HTML samples are vendored under `web/vendor/dads/`, with the MIT
license, exact source paths and commit recorded in NOTICE.md. The color tokens,
typography stack, buttons, selects and focus rings are used directly.
The application adds a custom keyboard diagram and responsive layout, explicit
labels, visible keyboard focus, textual change markers, live operation status,
and at least 44px targets for joystick controls. No official government logo or
claim of government endorsement is used. This is implementation based on DADS;
it has not undergone an independent accessibility conformance audit.

## Verification on 2026-10-15

- Node tests: twenty passing cases, including original-app x86 packet fixtures,
  report-ID handling, header validation, stale snapshots, storage failure,
  exclusive operation cleanup and backup integrity.
- Desktop Chrome on the user's PC: authorized `USB Keyboard`, read configuration
  through WebHID, changed the upper-left key from Q to F13, and successfully
  verified the saved region in the UI. Python independently read `68 FF FF FF
  FF FF FF FF` at `0x0128`.
- Restored Q through the WebHID UI and confirmed read-back success.
- GUI rendering and the demo were checked in desktop and mobile-width layouts.
- Python CLI: changed wheel byte `10 → 20 → 23`, verified complete configuration
  readback, then restored `10`. The user confirmed scrolling in custom mode and
  volume changes after restoration without USB reconnect using the corrected CLI.
- The initial implementation incorrectly required a stick push as a workaround.
  This was not established as original-app behavior. Replaying the current
  control block restored immediate scrolling without a stick push or USB reconnect
  in a user-operated hardware test. LED effects remain unverified.
- WebHID UI: changed both wheel directions from `10` to `23` in one commit and
  restored `10`; both saves passed the complete 248-byte readback comparison.

The extended action and macro implementation is described in [MACROS.md](MACROS.md).
Python has sixteen passing tests. The original x86 mapper and serializer provide
reference vectors for 26 menu choices and nine macro examples, including movement,
long delay and repetition modes. Physical tests confirmed Ctrl+F13 press/release,
volume-up and LED-mode switching. LED toggle did not react on this unit.
Other individual actions, sustained repetition, other OSes and firmware versions
are not established by these tests.

## Reinvestigation of inactive wheel settings

The manufacturer's K810 download was fetched again on 2026-10-15. Its ZIP hash
still matched the source recorded in PROTOCOL.md. `tools/trace_vendor_apply.py`
emulates the complete no-macro Apply path `0x410239..0x412528`, intercepting all
HID and Sleep calls; this synthetic trace is distinct from a USB capture.
`tests/vendor_apply_vectors.json` records both `KEYSMODE=0` and `KEYSMODE=1`.
The original writes the control block before the wheel byte. The control byte's
bit 7 comes from `KEYSMODE`; other bits contain unrelated settings and are
preserved by this implementation. Python now has twelve passing test cases.
The corrected WebHID UI also passed a user-operated scrolling test immediately
after saving, with no stick push and no USB reconnect. Both directions were then
restored to their values at the start of this reinvestigation.
