# Working on Modbus Tap

Notes for anyone changing this repository, human or AI assistant.

## Read first

- [GLOSSARY.md](GLOSSARY.md): use these words, in code and in text. Bus, Poller, Unit, Register, Transaction, Write, Bridge, Recording, Register map, Community map, Override.
- [docs/adr/](docs/adr/): decisions that are hard to reverse. Don't undo one without writing a new ADR that supersedes it. The big ones:
  - Modbus Tap never transmits (0001).
  - One device per Unit (0002).
  - Community maps plus Overrides (0003).
  - The core Modbus sensor format (0004).

## Code

- **Two layers.** Plain Python, with no Home Assistant imports and tested with plain pytest in `tests/`:
  - `model`, `rtu`, `values`, `register_map`, `community`, `store`, `bridge`, `recording`, `export`, `hints`

  Home Assistant glue, tested in `tests_ha/` with `pytest-homeassistant-custom-component`:
  - `tap`, `session`, `issues`, the platforms, flows, `services`, `download`, `diagnostics`, `repairs`

  Keep logic in the first layer.
- **SOLID, DRY, YAGNI.** Small modules with one job. One implementation of each rule: value decoding follows core Modbus in `values.py`, and nowhere else. Don't build features ahead of a real need; record "not yet" decisions in docs or ADRs.
- **Home Assistant practice:**
  - typed `runtime_data`
  - push updates, no polling
  - translated entity names, errors and issues
  - actions registered in `async_setup`
  - `probatio` for schemas
  - no blocking I/O in the event loop
- **The Tap must never write to the Bridge socket.** Tests assert that nothing is sent. Keep them.

## Register maps

- Community maps live in `custom_components/modbus_tap/community_maps/`, one YAML file per model, validated by `docs/register-map.schema.json`.
- Only set `documented` with a real source, and `verified` with the device and firmware it was checked on. Everything else stays guessed. Never upgrade a guess without evidence.
- To work out a map from a recording, follow [docs/working-out-a-register-map.md](docs/working-out-a-register-map.md).

## Writing

README, docs and UI text: upbeat, direct, no fluff. Short sentences, concrete steps, plain words. Safety warnings stay prominent in the hardware guide.

## Checks

`pytest tests` must pass locally. GitHub Actions also runs the Home Assistant tests, hassfest and the HACS validation.
