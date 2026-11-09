# Register maps

A register map tells Modbus Tap what the registers on a unit mean: name, data type, scale, unit. Each unit on your bus has its own map. Edit it under **Configure → Sensors**: go to **Settings → Devices & services → Modbus Tap**, click **Configure** on your bridge's entry, choose **Sensors** and pick the unit. The screen shows what the poller reads from that unit, which community maps exist (with how many entries are documented, verified or guessed), and suggests one when the unit matches ([more on finding Configure](finding-your-way.md#configure-the-settings-of-your-bus)).

## Format

Entries use the **sensor format of Home Assistant's core Modbus integration**, with the same keys, meanings and defaults. Sensor YAML you already have for core Modbus works unchanged.

```yaml
- name: Grid voltage
  address: 37
  input_type: input        # holding (default) or input
  data_type: uint16        # int16 (default), uint16, int32, uint32, int64, uint64,
                           # float16, float32, float64, string
  scale: 0.1               # value = raw × scale + offset
  precision: 1             # integers default to 0 decimals, floats to 2
  unit_of_measurement: V
  device_class: voltage
  state_class: measurement
  documented: "Vendor protocol v1.2, table 3"
```

Also supported, as in core: `count` (registers, required for strings), `swap` (`byte`, `word`, `word_byte`), `offset`, `nan_value`, `min_value`, `max_value`, `zero_suppress` and `device_address` (or the older `slave`).

`scan_interval` and `unique_id` are accepted and ignored, because Modbus Tap doesn't poll. Multi-value features (`data_type: custom` with `structure`, `slave_count`, `virtual_count`) aren't supported yet. Open an issue if you need them.

### Extra keys

| Key | Meaning |
|---|---|
| `documented` | Where the entry comes from, for example a protocol document and section |
| `verified` | Who checked it on which device and firmware, for example `SSE-HH6K-P1-EU, firmware V1.16` |
| `model: true` | This string register holds the unit's model. Modbus Tap uses it for the device model and to suggest community maps |

An entry can be documented, verified, both, or neither. Neither means **guessed**. Every mapped sensor shows this as its `map_status` attribute, so you know what to double-check.

### Defaults to watch

Like core Modbus, `input_type` defaults to `holding` and `data_type` to `int16`, and integers are rounded to whole numbers unless you set `precision`. A voltage stored as 2344 with `scale: 0.1` shows as 234 without `precision: 1`.

## Community maps and overrides

Community maps live in [`custom_components/modbus_tap/community_maps/`](../custom_components/modbus_tap/community_maps/) and ship with every release.

- Pick one as a unit's base. Your own entries then **override** community entries with the same table and address, and add anything new.
- Fixes to the community map reach you when you update Modbus Tap. Your own entries stay on top.
- Want full control instead? Copy the community entries into your own map and leave the base empty.

When a unit's traffic matches a community map, by its model text or by the registers its poller reads, Modbus Tap raises a repair suggesting it. It never applies a map on its own.

### Writing a community map

```yaml
name: SSE-HH6K hybrid inverter
manufacturer: Sosen
match:
  model_text: "^SSE-HH"               # regex on the register marked model: true
  reads: ["input 1-100", "input 101-203"]  # blocks the usual poller reads
sensors:
  - name: Model
    address: 144
    input_type: input
    data_type: string
    count: 8
    model: true
  # ...
```

Use `device_address` 1 in community maps. Modbus Tap moves entries to whichever unit you pick. The schema is in [register-map.schema.json](register-map.schema.json).

## Next

Don't know what your registers mean? [Working out a register map](working-out-a-register-map.md). Map complete and want Home Assistant to poll directly? [Replacing your poller](replacing-your-poller.md).
