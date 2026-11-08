# Register maps use the core Modbus sensor format

Entries in a **Register map** use the keys, meanings and defaults of the sensor configuration of Home Assistant's built-in Modbus integration (`address`, `input_type`, `data_type`, `count`, `swap`, `scale`, `offset`, `precision`, `nan_value`, `min_value`, `max_value`, `device_address`, units and classes), instead of a format of our own. Countless working core Modbus configurations for inverters and meters already exist in forums and repositories, and people should be able to paste them in unchanged. We only add what core has no notion of: `documented`, `verified`, and a marker for the register that holds the **Unit**'s model text.

## Considered Options

- **Our own, simpler format**: rejected; it duplicated core's concepts under different names and defaults, and made every existing configuration useless here.

## Consequences

- Defaults follow core, so `input_type` defaults to `holding` and `data_type` to `int16`, even though many inverters mostly use input registers.
- Keys that only make sense for active polling, such as `scan_interval`, are accepted and ignored with a notice. Core features that read several values from one block (`custom` with `structure`, `slave_count`, `virtual_count`) are rejected until someone needs them.
- The glossary term is **Unit address**; the YAML key is core's `device_address` (core's legacy `slave` is accepted too).
