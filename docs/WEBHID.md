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
The previously observed `2130:30FA` variant remains unsupported in the Web UI.
Chrome's protected keyboard input reports are not requested; the vendor
configuration collection is separately accessible.

## Write boundaries and recovery

- UI edits and imports affect only the 16 exposed control bytes.
- Each changed column is written as its original 8-byte block with the other
  seven bytes preserved. RGB, wheel columns, macros and configuration headers
  are never writable through the UI.
- Before writing, read the configuration again and compare with the session
  snapshot; concurrent changes cause an abort.
- Web Locks serialize USB operations between same-origin tabs. Close other
  configurators; locks cannot coordinate with native programs or other origins.
- Save a SHA-256 checked backup to localStorage **before** EEPROM commits. If
  storage is unavailable/full, abort. One latest recovery backup is kept.
- Read back and compare the complete 248-byte region after writing.
- A failure requires rereading the device before further edits are saved.
- Backups are compatible with the Python `mkespn-k810-config-v1` format. The Web
  backup has an empty `metadata_hex` and an additional `header_hex`, since the
  variable-length native metadata request is unavailable.
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

- Node tests: ten passing cases, including original-app x86 packet fixtures,
  report-ID handling, header validation, stale snapshots, storage failure,
  exclusive operation cleanup and backup integrity.
- Desktop Chrome on the user's PC: authorized `USB Keyboard`, read configuration
  through WebHID, changed the upper-left key from Q to F13, and successfully
  verified the saved region in the UI. Python independently read `68 FF FF FF
  FF FF FF FF` at `0x0128`.
- Restored Q through the WebHID UI and confirmed read-back success.
- GUI rendering and the demo were checked in desktop and mobile-width layouts.

Actual physical keypress events, persistence across USB reconnect, other OSes,
and other hardware/firmware versions are not part of this verification.
