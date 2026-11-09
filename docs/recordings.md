# Recordings

A recording logs everything that happens on the bus, timestamped, together with values from other sources you already trust and notes you add. It's the raw material for [working out a register map](working-out-a-register-map.md).

## How it fits together

A recording is **just a file**. It doesn't change your sensors by itself. The path from recording to sensors:

1. **Record** a few hours, with reference sources set (below).
2. **Suggest a register map:** **Configure → Recordings → Suggest a register map from a recording**. Modbus Tap finds the registers that follow your reference entities and works out their scale. Optionally, an AI refines it. [How it works](#4-suggest-a-register-map)
3. **Review and save** the suggested entries. They're added to the unit's own entries and the sensors appear.
4. **Compare** them with your reference values for a day and fix what's off.

Prefer to work it out yourself, or with an AI assistant outside Home Assistant? Download the file and follow [Working out a register map](working-out-a-register-map.md).

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

- **Right away:** a notification (the bell) links to the finished recording.
- **Later:** **Configure → Recordings → Download or delete recordings** lists every recording with a fresh download link, and lets you delete the ones you don't need.

Download links work for 24 hours, and stop working when Home Assistant restarts (after an update, say). The recording itself stays; an expired link tells you so and where to get a fresh one.

Modbus Tap keeps your 20 most recent recordings by default; change this under **Configure → Recordings → Reference sources and storage**. The files are in your config folder under `modbus_tap/recordings/`, if you prefer the Samba or File editor add-on.

What's inside a recording is described in [Recording format](recording-format.md).

## 4. Suggest a register map

**Configure → Recordings → Suggest a register map from a recording.** Pick a recording and a unit. Modbus Tap then:

- **Matches counters on their rate.** Energy totals all rise together, so correlation can't tell them apart. For a reference that only goes up, Modbus Tap looks for the register that rises at the same rate, at a round scale. The two may differ by a fixed amount (a cloud total that missed some energy, say), and today's counter is told apart from the lifetime total by how close the values are.
- **Ignores a reference source that gave up.** When most reference entities drop to 0 or unavailable at the same moment, those zeros are skipped: the cloud stopped reporting, the inverter didn't stop producing.
- **Allows for lag.** Cloud integrations report what the device did a few minutes ago; Modbus Tap tries delays of up to ten minutes and uses the one that fits.
- **Matches registers to reference entities.** For each reference entity, it looks for the register (or pair of registers, for 32-bit values) that follows it, and the scale that turns one into the other: ×0.1 for a voltage read as 2348, say. Only the scales devices use count (1, 0.1, 0.01 and so on); a register that follows a reference at some other factor is a different quantity.
  - With enough values (6 or more changes per entity), it uses correlation. Close matches get `verified`, with the entity and recording as evidence.
  - With only a few values, it matches the values themselves and leaves the entry unverified. Cloud integrations often update every five minutes, so a ten-minute recording gives each entity two or three values. Record a few hours for stronger matches.
- **Leaves out what you already have right.** Entries your current map already has, with the same type and scale, are counted but not suggested again.
- **Shows you the result** to edit. Submitting adds the entries to the unit's own entries: an entry at the same address replaces yours, everything else stays.

Names, units and device classes come from the reference entities. Check them: a cloud integration's "PV Pac" is your call to rename.

### Ask an AI too (optional)

If you've set up an **AI Task** in Home Assistant (through OpenAI, Google Gemini, Anthropic, Ollama or another AI integration), pick it in the **Also ask an AI** field. The AI gets a summary of the recording, not the file: the registers that changed with sample values, text found, the reference entities and Modbus Tap's own matches. It can add what correlation can't find, such as counters, states and settings.

Modbus Tap checks the AI's answer before showing it:

- It has to be a valid register map. If it isn't, or the AI doesn't answer, you get Modbus Tap's own matches with a note.
- Entries with a scale no device uses (anything other than 1, 0.1, 0.01, 0.001, 10 and so on) are left out. An odd scale like `0.0003` or `22.67` means the register moves along with the reference without being the same thing: the PV current against PV power, say.
- `verified` is only kept where Modbus Tap's own matching backs the entry up, with that as the evidence.

An AI can still be confidently wrong, so treat its entries as guesses until they've matched your reference values for a while.

The summary includes your reference entity IDs and values, and goes to whichever AI provider your AI Task uses.

## Questions

**Does a recording create sensors by itself?**
No. Use **Suggest a register map** (above), or work it out from the downloaded file. Nothing changes until you save.

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

[Working out a register map](working-out-a-register-map.md): the method behind the suggestions, for doing it by hand or with an AI assistant.
