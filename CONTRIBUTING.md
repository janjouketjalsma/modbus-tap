# Contributing

Thanks for helping out! The most valuable contribution is a register map for a device you own.

## Add or improve a community map

1. Work out the registers ([how](docs/working-out-a-register-map.md)) and check them in Home Assistant for a day.
2. Add or edit a file in [`custom_components/modbus_tap/community_maps/`](custom_components/modbus_tap/community_maps/), one per model. The format is in [Register maps](docs/register-maps.md#writing-a-community-map).
3. Be honest about confidence:
   - `documented: "<source>"` only when you took it from a written source. Name the document and section.
   - `verified: "<model>, firmware <version>"` only when you checked it against a real value on that device.
   - Neither, if it's a good guess. Guesses are welcome, and someone else can verify them later.
4. Run `pytest tests` (it checks every map against the schema) and open a pull request.

Never include serial numbers or other details that identify your own installation.

## Report a problem

Open an issue with:

- your Home Assistant and Modbus Tap versions
- your bridge and how it's set up
- the diagnostics download (integration page → ⋮ → **Download diagnostics**). Remove serial numbers before posting.

## Change the code

Read [AGENTS.md](AGENTS.md) first. It covers the structure, conventions and the decisions not to undo.
