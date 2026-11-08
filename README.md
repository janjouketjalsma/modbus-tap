# Modbus Tap

![Modbus Tap icon](custom_components/modbus_tap/brand/icon.png)

Listen in on a Modbus RTU bus that's already in use, and turn what goes past into Home Assistant sensors. **Modbus Tap never transmits.** Your inverter's logger, dongle or meter keeps working exactly as before.

It's for buses that already have a poller, such as a solar inverter with a vendor Wi-Fi dongle or a heat pump with its own controller. Polling them yourself would make a second master and risk collisions. Modbus Tap just listens.

## What you get

- **Plug-in setup:** add the integration, enter your RS485 bridge's address, done.
- **One device per unit:** every Modbus unit on the bus shows up as its own device.
- **Core Modbus register maps:** existing core Modbus sensor YAML pastes right in.
- **Community maps:** ready-made maps you can use as a base and correct where needed. Modbus Tap suggests one when your device matches.
- **Recordings:** a timestamped log of all bus traffic, alongside other Home Assistant values and your own notes. That's everything you need to work out an unknown register map, with or without an AI assistant.
- **Writes:** see what the poller writes, and whether the device accepted it. Optionally, you also get an event for each write.
- **Export to core Modbus:** ready to replace the vendor dongle? Export your map as `modbus:` YAML.

## How it compares

| | Modbus Tap | ESPHome sniffer¹ | ESPHome | HA Modbus |
|---|---|---|---|---|
| Listens only (safe next to your logger) | ✅ | ✅ | ❌ | ❌ |
| Hardware | Network bridge | ESP32 + RS485 | ESP + RS485 | USB or network |
| Setup | UI | YAML + flash | YAML + flash | YAML |
| Helps find unknown registers | ✅ | ❌ | ❌ | ❌ |
| Register format | Core Modbus | ESPHome | ESPHome | Core Modbus |
| Shared maps | ✅ | ❌ | Some meters | ❌ |
| Controls the device | ❌ | ❌ | ✅ | ✅ |
| Status | New | In review | Stable | Stable |

¹ In development: [esphome/esphome#19450](https://github.com/esphome/esphome/pull/19450)

## Install

1. In Home Assistant, open **Settings → Marketplace** (HACS before 2026.11), choose **Add from link** and paste `https://github.com/janjouketjalsma/modbus-tap`.
2. Install **Modbus Tap**.
3. **Settings → Devices & services → Add integration → Modbus Tap**, and enter your bridge's address and port.

## Docs

| Guide | For |
|---|---|
| [Tapping your bus](docs/tapping-your-bus.md) | Finding the pins with a multimeter, building a tap cable, wiring and setting up the bridge, troubleshooting |
| [Register maps](docs/register-maps.md) | The map format, community maps and overrides, documented and verified |
| [Working out a register map](docs/working-out-a-register-map.md) | Recordings, diagnostics and an AI-ready method and prompt |
| [Recording format](docs/recording-format.md) | The file format, for scripts and assistants |
| [Replacing your poller](docs/replacing-your-poller.md) | Moving to core Modbus once your map is complete |
| [Decisions](docs/adr/) and [glossary](GLOSSARY.md) | Why things are the way they are, and what the words mean |

## Contributing

Know what a register means? Add it to a community map in [`community_maps/`](custom_components/modbus_tap/community_maps/) and open a pull request. Mark each entry `documented` (with its source) or `verified` (with the device and firmware you checked it on). Guesses are welcome too: leave both out. See [AGENTS.md](AGENTS.md) for code conventions.

## License

MIT
