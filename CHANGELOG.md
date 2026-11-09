# Changelog

All notable changes to Modbus Tap. Versions follow [Semantic Versioning](https://semver.org); see [Versioning](docs/versioning.md) for what counts as breaking.

## [Unreleased]

## [0.6.1] - 2026-11-09

### Fixed

- Suggestions no longer contain odd scales such as `0.0003035` or `22.67`. Only the scales devices use (1, 0.1, 0.01, 0.001, 10, and their negatives) count as a match; a register that follows a reference at another factor is a different quantity.
- The AI's suggestions are checked against the recording: entries with an odd scale are left out, and `verified` is only kept where Modbus Tap's own matching backs the entry up. The suggestion screen says what was changed.

If you saved suggestions from 0.5.0 or 0.6.0, check them under **Configure → Sensors** for odd scales and unearned `verified` notes.

## [0.6.0] - 2026-11-09

### Added

- **Configure → Writes:** what the poller writes, how often, and every change in value, kept across restarts. Repeated writes of the same values count as one change, and the history is capped at 100 register blocks with 50 changes each, so it stays small. Registers in your map are shown by name.
- Suggest a register map passes the poller's writes to the AI too, so it can name settings.
- Diagnostics include the write history.
- New guide: [Writes](docs/writes.md), including what to consider before writing to your devices yourself.

## [0.5.0] - 2026-11-09

### Added

- **Suggest a register map from a recording** (Configure → Recordings). Modbus Tap matches registers to your reference entities, works out data type and scale, and leaves out what your current map already has right. You review and edit the entries; saving adds them to the unit's own entries.
  - Matches on correlation when reference entities changed often enough (marked `verified`), and on values when they changed only a few times, as cloud integrations that update every five minutes do in short recordings.
  - Optional: pick an AI Task entity to have an AI refine the suggestion from a summary of the recording. If its answer isn't a valid map, you get Modbus Tap's own matches.

## [0.4.2] - 2026-11-09

### Changed

- Recordings explain what happens next: a recording is a file you turn into a register map and paste under Sensors; it doesn't create sensors by itself. Same in the docs, with answers about keeping reference sources and what happens when one becomes unavailable (nothing breaks).

## [0.4.1] - 2026-11-09

### Fixed

- Saving **Configure → Recordings → Reference sources and storage** failed with an error in 0.4.0.
- Releases are only published once all tests pass.

## [0.4.0] - 2026-11-09

### Changed

- ⚠️ Breaking (menu only, no settings lost): Configure is reorganised by task. **Sensors** (was Register maps), **Recordings** with **Start or stop a recording**, **Reference sources and storage** and **Download or delete recordings**, **Export to core Modbus**, and **Advanced** (write events). Reference sources moved from Settings to Recordings.
- Configure screens explain what they found: the status of the bridge, units heard with model and map, what the poller reads from a unit, and how many community-map entries are documented, verified or guessed. A matching community map is preselected.
- Changing reference sources, storage or write events no longer reloads Modbus Tap, so a running recording keeps going. Only saving a register map reloads.

### Added

- Start a recording from Configure, with a duration and a preview of which reference entities will be logged.

## [0.3.1] - 2026-11-09

### Added

- A notification when a recording starts without reference sources, explaining where to set them.
- Docs: [Finding your way around](docs/finding-your-way.md) (where Configure and everything else live) and [Recordings](docs/recordings.md) (reference devices, patterns and entities, downloading, actions with examples).

## [0.3.0] - 2026-11-09

### Added

- Reference entity patterns for recordings, such as `sensor.solarsynkv3_*`. For sources that post sensors without a device, like the SolarSynk v3 add-on. Available in Settings and as `reference_patterns` on `modbus_tap.start_recording`.

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

[Unreleased]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/janjouketjalsma/modbus-tap/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/janjouketjalsma/modbus-tap/releases/tag/v0.1.0
