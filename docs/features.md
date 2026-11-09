# Features

Everything Modbus Tap does, with links to the details.

## Listening

- **Never transmits.** Modbus Tap only reads from the bridge. It's safe next to the logger, dongle or controller that already polls your bus ([why](adr/0001-passive-only.md)).
- **Decodes Modbus RTU** from any network bridge in transparent mode: reads of holding and input registers, coils and discrete inputs, and writes.
- **Reconnects by itself** when the bridge drops the connection.

## Devices and sensors

- **One device per unit.** Every unit address on the bus becomes a Home Assistant device, connected via a bridge device ([why](adr/0002-one-entry-per-bus-one-device-per-unit.md)).
- **Named, scaled sensors** from each unit's [register map](register-maps.md), in the core Modbus sensor format.
- **The model comes from the device.** The model is read from the unit itself when its map marks a model register.
- **Stale values go unavailable** after three missed polls (never sooner than five minutes), so a stopped logger doesn't leave frozen numbers behind.
- **Bridge health sensors:** connection and the running recording update right away; the frames decoded and bytes discarded counters update every 30 seconds, so they don't flood your history.

## Register maps

- **Core Modbus format.** Existing core Modbus sensor YAML pastes straight in ([why](adr/0004-register-maps-use-core-modbus-sensor-format.md)).
- **Community maps** ship with each release. Use one as a base and override entries where your device differs ([why](adr/0003-community-map-plus-overrides.md)).
- **Suggestions.** When a unit matches a community map, by its model text or by what its poller reads, a repair offers it. Nothing is applied without you.
- **Documented, verified or guessed.** Each sensor's `map_status` attribute says how far to trust it.

## Recordings

All the details: [Recordings](recordings.md).


- **Start and stop** with buttons on the bridge device, or with the `modbus_tap.start_recording` and `modbus_tap.stop_recording` actions.
- **Reference devices and entities:** log other Home Assistant values alongside the bus traffic. Pick a whole device, such as your inverter's cloud integration, or a pattern like `sensor.solarsynkv3_*`, to get all its sensors at once.
- **Notes:** add your own with `modbus_tap.add_note` ("kettle on").
- **Managed in Home Assistant:** download and delete under **Configure → Recordings** ([where's Configure?](finding-your-way.md#configure-the-settings-of-your-bus)). Old ones are cleaned up automatically, and a notification links to each finished recording.
- **Documented format** for scripts and AI assistants ([format](recording-format.md), [method and prompt](working-out-a-register-map.md)).

## Writes

- **Values the poller writes** update the register once the unit confirms them. Rejected and unanswered writes are ignored.
- **Optional `modbus_tap_write` event** for each write, with the outcome (`confirmed`, `rejected`, `unanswered`). Turn it on under **Configure → Settings**.

## Help when things go wrong

- **Repairs for common tap problems:** nothing heard, data that looks like swapped A/B wires, and data that looks like a wrong baud rate. Each links to the [troubleshooting table](tapping-your-bus.md#troubleshooting).
- **Diagnostics download** with every register heard, its statistics and hints (*mains voltage ×0.1 V?*, *probably signed*, *only increases*), plus any text found.

## Moving on

- **Export to core Modbus:** **Configure → Export** gives ready-to-paste `modbus:` YAML for replacing your poller ([guide](replacing-your-poller.md)).
