# Changelog

All notable changes to Modbus Tap. Versions follow [Semantic Versioning](https://semver.org); see [Versioning](docs/versioning.md) for what counts as breaking.

## [Unreleased]

## [0.2.0] - 2026-11-09

### Added

- Reference devices for recordings: pick a device, such as your inverter's cloud integration, and all its sensors are logged next to the bus traffic. Available in Settings (for the Start recording button) and as `reference_devices` on the `modbus_tap.start_recording` action.

## [0.1.1] - 2026-11-09

### Fixed

- Recording download links now work in the Home Assistant companion apps: they open as a download instead of jumping back to the main page.

## [0.1.0] - 2026-11-08

First release.

### Added

- Listen-only connection to a network RS485 bridge, decoding Modbus RTU reads and writes. Modbus Tap never transmits.
- One Home Assistant device per unit on the bus, linked via a bridge device.
- Register maps in the core Modbus sensor format, edited in the UI, with community maps as a base and your own overrides on top.
- Community maps: Sosen SSE-HH6K hybrid inverter (mostly guessed), Chint DDSU666 energy meter (documented).
- Map suggestions as repairs when a unit matches a community map.
- Recordings with reference entities and notes, managed under Configure, with download links.
- Optional `modbus_tap_write` events with the outcome of each write.
- Repairs for a silent bus, likely swapped A/B wires and a likely wrong baud rate.
- Diagnostics with every register heard and hints.
- Export to core Modbus YAML.

[Unreleased]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/janjouketjalsma/modbus-tap/releases/tag/v0.1.0
