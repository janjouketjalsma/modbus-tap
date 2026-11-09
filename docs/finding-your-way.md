# Finding your way around

Modbus Tap puts things in three places in Home Assistant. Most settings live behind **Configure**, which is easy to miss.

## Configure (the settings of your bus)

1. Go to **Settings → Devices & services**.
2. Open **Modbus Tap**.
3. Find your bridge's entry. It's named after the bridge address, for example `192.168.1.120:8899`.
4. Click **Configure** on that entry. Depending on your Home Assistant version, it's a button on the entry, or under the entry's **⋮** menu.

The Configure menu opens with the current status (bridge connected, units heard, recording on or off) and is organised by what you want to do:

| Menu item | What it's for |
|---|---|
| **Sensors** | Pick a unit, choose a community map and add your own entries. The screen shows what the poller reads and suggests a matching map ([guide](register-maps.md)) |
| **Recordings** | **Start or stop a recording**, **Reference sources and storage** (what to log next to the bus traffic, how many recordings to keep), **Download or delete recordings**, **Suggest a register map from a recording** ([guide](recordings.md)) |
| **Writes** | What the poller writes, and when the values change ([guide](writes.md)) |
| **Export to core Modbus** | Get `modbus:` YAML for replacing your poller ([guide](replacing-your-poller.md)) |
| **Advanced** | Write events |

Only saving a unit's register map reloads Modbus Tap. Everything else takes effect right away, so a running recording keeps going.

In these docs, **Configure → Recordings** means: open Configure as above, then choose **Recordings**.

## The bridge device

**Settings → Devices & services → Modbus Tap**, then open the device named **Bridge** followed by your bridge's address. It has:

- **Start recording** and **Stop recording** buttons
- **Connection**, **Recording**, **Frames decoded** and **Bytes discarded** sensors, which tell you whether the tap is healthy

## Unit devices

Each Modbus unit heard on the bus gets its own device, named **Unit 1**, **Unit 2** and so on. Rename them to something meaningful, such as "Inverter". Their sensors come from the unit's register map.

## Other places

- **Repairs** (**Settings → System → Repairs**): Modbus Tap's suggestions, such as "use this community map", and warnings about tap problems.
- **Notifications** (the bell): a link to each finished recording.
- **Actions** (**Developer tools → Actions**, or in automations): `modbus_tap.start_recording`, `modbus_tap.stop_recording` and `modbus_tap.add_note`.
- **Diagnostics** (integration page → your entry's **⋮** → **Download diagnostics**): every register heard, with hints.
