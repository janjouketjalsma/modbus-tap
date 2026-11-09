# Recordings

A recording logs everything that happens on the bus, timestamped, together with values from other sources you already trust and notes you add. It's the raw material for [working out a register map](working-out-a-register-map.md).

## How it fits together

A recording is **just a file**. It doesn't change your sensors and doesn't create a register map by itself. The full path looks like this:

1. **Record** a few hours, with reference sources set (below).
2. **Download** the file.
3. **Turn it into a register map:** hand it to an AI assistant with [the prompt](working-out-a-register-map.md#prompt-for-an-ai-assistant), or work through it yourself with [the method](working-out-a-register-map.md#2-analyse). The result is a block of YAML.
4. **Paste the YAML** into **Configure → Sensors**, pick the unit, and put it under **Your entries**. The sensors appear.
5. **Compare** them with your reference values for a day and fix what's off.

Doing the analysis inside Home Assistant (with its AI Task feature) is planned for a later version.

## 1. Choose your reference sources

Reference sources are your answer key: values Modbus Tap writes into the recording next to the bus traffic, so registers can be matched against them. Set them once under **Configure → Recordings → Reference sources and storage** ([where's Configure?](finding-your-way.md#configure-the-settings-of-your-bus)):

| Setting | Use it for | Example |
|---|---|---|
| **Reference devices** | An integration that groups its sensors under a device. Every sensor of the device is logged. | The device of your inverter's cloud integration |
| **Reference entity patterns** | Sensors without a device, such as those posted by an add-on. Use `*` as a wildcard. | `sensor.solarsynkv3_*` for the SolarSynk v3 add-on |
| **Extra reference entities** | Single sensors from anywhere | A smart plug's power sensor |

Changing them doesn't interrupt a running recording; they're used from the next start. Combine them as you like. Only `sensor` and `binary_sensor` entities are picked up by devices and patterns.

Not sure what your entities are called? Look them up under **Settings → Devices & services → Entities**, and search for the integration or add-on name.

## 2. Record

1. Press **Start recording** on the **bridge device** (**Settings → Devices & services → Modbus Tap →** the device named **Bridge …**), or use **Configure → Recordings → Start or stop a recording**, which also shows which reference entities will be logged and lets you pick a duration.
2. Let it run for a few hours while things change: sunrise, clouds, the oven on, the car charging. Two minutes at night shows almost nothing moving.
3. Add notes for things the reference sources can't see, for example "kettle on" or "app shows 2.1 kW solar". Use the `modbus_tap.add_note` action from a dashboard button or a phone shortcut. There's an example below.
4. Press **Stop recording**. Recordings also stop on their own after 24 hours.

The **Recording** sensor on the bridge device shows the name of the running recording.

## 3. Download

- **Right away:** a notification (the bell) links to the finished recording. The link works for one hour.
- **Later:** **Configure → Recordings → Download or delete recordings** lists every recording with a fresh download link, and lets you delete the ones you don't need.

Modbus Tap keeps your 20 most recent recordings by default; change this under **Configure → Recordings → Reference sources and storage**. The files are in your config folder under `modbus_tap/recordings/`, if you prefer the Samba or File editor add-on.

What's inside a recording is described in [Recording format](recording-format.md).

## Questions

**Do I need to keep the reference sources set?**
No. They're only used while recording. Once your register map works, clear them under **Configure → Recordings → Reference sources and storage**, or leave them. They cost nothing when you're not recording.

**What if a reference device or entity becomes unavailable, or is removed?**
Nothing breaks. Listening to the bus and your sensors don't depend on reference sources at all. During a recording, an unavailable entity is logged as `unavailable`, which an analysis simply skips. A removed device or entity, or a pattern that matches nothing, is skipped when the next recording starts.

**Does a recording affect the bus or my sensors?**
No. Recording only writes a file; Modbus Tap never transmits, recording or not.

## From automations and dashboards

The actions accept their own reference sources. Leave them all out to use the ones set under **Configure → Recordings → Reference sources and storage**.

```yaml
# Record three hours from sunrise, with the SolarSynk sensors as reference
automation:
  - alias: Record the morning on the bus
    triggers:
      - trigger: sun
        event: sunrise
    actions:
      - action: modbus_tap.start_recording
        data:
          config_entry: <your Modbus Tap entry>
          hours: 3
          reference_patterns:
            - "sensor.solarsynkv3_*"
```

```yaml
# A dashboard button that adds a note
type: button
name: Kettle on
tap_action:
  action: perform-action
  perform_action: modbus_tap.add_note
  data:
    config_entry: <your Modbus Tap entry>
    text: kettle on
```

When you create these in the UI editor, the **Bus** field lets you pick your Modbus Tap entry, so you don't need to know its ID.

| Action | Fields |
|---|---|
| `modbus_tap.start_recording` | `config_entry`, `hours` (default 24, at most 24), `reference_devices`, `reference_patterns`, `reference_entities` |
| `modbus_tap.stop_recording` | `config_entry` |
| `modbus_tap.add_note` | `config_entry`, `text` |

## Next

[Working out a register map](working-out-a-register-map.md): turning a recording into a map.
