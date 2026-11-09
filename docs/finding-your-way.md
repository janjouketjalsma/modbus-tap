# Finding your way around

Modbus Tap puts things in three places in Home Assistant. Most settings live behind **Configure**, which is easy to miss.

## Configure (the settings of your bus)

1. Go to **Settings → Devices & services**.
2. Open **Modbus Tap**.
3. Find your bridge's entry. It's named after the bridge address, for example `192.168.1.120:8899`.
4. Click **Configure** on that entry. Depending on your Home Assistant version, it's a button on the entry, or under the entry's **⋮** menu.

The Configure menu has four parts:

| Menu item | What it's for |
|---|---|
| **Register maps** | Pick a unit, choose a community map and add your own entries ([guide](register-maps.md)) |
| **Recordings** | Download and delete recordings ([guide](recordings.md)) |
| **Export to core Modbus** | Get `modbus:` YAML for replacing your poller ([guide](replacing-your-poller.md)) |
| **Settings** | Reference sources for recordings, write events, how many recordings to keep |

In these docs, **Configure → Settings** means: open Configure as above, then choose **Settings**.

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
