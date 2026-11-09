# Working out a register map

No documentation for your device? You can still work out what most registers mean. This is the method that worked on a real inverter, written for people and AI assistants alike.

Modbus Tap does the first part for you: **Configure → Recordings → Suggest a register map from a recording** matches registers against your reference entities ([how](recordings.md#4-suggest-a-register-map)). This page is for the rest: registers without a reference entity, or doing it all by hand or with an AI assistant of your choice.

## 1. Record

Make a [recording](recordings.md) of a few hours with your reference sources set: the values you already have from somewhere else, such as your inverter's cloud integration or add-on. They're your answer key. Add notes for things they can't see ("kettle on").

## 2. Analyse

Do it yourself with a script, or hand the recording to an AI assistant with the prompt below. Either way, the method is:

1. **Group by unit and table.** Each `transaction` line holds a block of registers that was read (`outcome: answered`) or written (`outcome: confirmed`).
2. **Find text.** Runs of registers whose bytes are printable ASCII are model names, serial numbers and firmware versions. Map them as `data_type: string` with `count`.
3. **Find types:**
   - Values near 65535 that hop around zero are signed: `int16`.
   - Pairs of registers where one changes slowly and the next one wraps are 32-bit values: `uint32` or `int32`, and try `swap: word` if they look reversed.
   - Values that only ever increase are energy counters: `state_class: total_increasing`.
4. **Find scale.**
   - Mains voltage shows up as about 2300 (×0.1 V), and frequency as about 5000 (×0.01 Hz).
   - Current is often ×0.1 or ×0.01 A, and power in whole W or ×0.1.
5. **Match against reference entities and notes.**
   - Line a register up with a reference entity over time. A register that rises and falls with your solar power, at a constant ratio, is solar power, and that ratio is the scale.
   - Notes mark moments to look at: what changed when the kettle went on?
6. **Find settings.** Registers that never change, especially in the holding table, are usually settings and limits. Low priority unless you need one.
7. **Mark your confidence.**
   - **Matched against a reference value:** `verified`, with your model and firmware.
   - **Taken from a document:** `documented`, with the source.
   - **Neither:** leave both out, so the entry counts as guessed.

The diagnostics download (integration page → ⋮ → **Download diagnostics**) gives the current snapshot with hints such as *mains voltage ×0.1 V?*, *probably signed* and *only increases*, plus any text found. It's a quick first look before a full recording.

## 3. Check in Home Assistant

Paste the map into **Configure → Sensors**, pick the unit, and put it under **Your entries** ([where's Configure?](finding-your-way.md#configure-the-settings-of-your-bus)) and compare the new sensors with your reference values for a day. Fix the scale, sign or type where they don't match. When you're happy, consider contributing the map so the next person with the same device starts from yours.

## Settings: change one and watch

Settings (export limits, charge currents, grid protection) rarely change on their own, and cloud integrations usually don't report them, so there's nothing to match against. Change them yourself instead:

1. Start a recording.
2. Change **one** setting in the manufacturer's app, and add a note saying what you changed, from what to what: "export limit 6000 → 5000 W".
3. Wait for the poller to read the settings block again (a few minutes), then change it back, with another note.
4. In the recording, the register that changed to your value and back at those moments is that setting.

Only change settings you understand, and never grid protection settings: those are set for your grid connection.

## Prompt for an AI assistant

Attach the recording (and the diagnostics file, if you have it), then paste:

```text
You are helping me work out the Modbus register map of my device from a
Modbus Tap recording. The recording is gzip-compressed JSON Lines; the
format is described at
https://github.com/janjouketjalsma/modbus-tap/blob/main/docs/recording-format.md

Method:
1. Decode the file. Group "transaction" records by unit and table; track how
   each register changes over time ("t" is a Unix timestamp).
2. Find ASCII strings, signed values, 32-bit pairs (try both word orders),
   counters that only increase, and constant settings.
3. Line registers up against the "entity" records (my reference values, with
   units) and the "note" records. Estimate the scale factor for each match.
4. Use typical ranges as hints: mains voltage ~2300 (x0.1 V),
   frequency ~5000 (x0.01 Hz).

Output: a YAML list in the Home Assistant core Modbus sensor format (name,
address, input_type, data_type, count, swap, scale, precision,
unit_of_measurement, device_class, state_class). Add "verified: <model,
firmware>" only to entries you matched against a reference entity; leave
everything else without it. Validate the result against
https://github.com/janjouketjalsma/modbus-tap/blob/main/docs/register-map.schema.json
List what you could not identify, and say how confident you are about each
entry.
```

Check the result against your reference values before trusting it.

## Next

- [Register maps](register-maps.md): every key in the format
- [Recording format](recording-format.md): the file, field by field
- [Contributing](../CONTRIBUTING.md): share your map
