# Modbus Sniffer for Home Assistant

Listen in on an existing Modbus RTU (RS485) bus and turn the values that go
past into Home Assistant sensors, **without ever transmitting on the bus**.

Typical use: an inverter is already polled by a vendor dongle or data logger
(for example an Elinter Magpie), and you want the same data in Home Assistant
without adding a second Modbus master that could collide with it.

```
inverter ⇄ RS485 ⇄ vendor dongle (master)
                │
                └── TCP-to-RS485 bridge (e.g. Elfin EW11) ──Wi-Fi──► Home Assistant (listens only)
```

## How it works

1. A serial-to-network bridge sits on the bus in **transparent** mode and
   forwards every byte it hears over TCP.
2. The integration connects to it, splits the stream into Modbus RTU frames
   using the CRC, pairs each request with its response, and keeps a table of
   every register value it has seen (holding and input registers, coils,
   discrete inputs, and values written with function 6/16).
3. Sensors are created from that table:
   - **Raw sensors**: one per register, created automatically the first time
     it is seen. They are disabled by default; enable the ones you want to
     watch. Attributes show hex, signed value, ASCII, min/max and how often it
     changed.
   - **Mapped sensors**: named, scaled sensors with units and device classes,
     defined in a small YAML register map from the UI.
   - **Status sensors**: connection state, frames decoded, bytes discarded,
     registers seen, and the time of the last frame.

You only get the registers the existing master asks for, at the rate it asks
for them.

## Installation (HACS)

1. HACS → three dots → **Custom repositories** → add this repository's URL
   with type **Integration**.
2. Install **Modbus Sniffer** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Modbus Sniffer**, and
   enter the bridge's IP address and port (8899 by default on Elfin devices).

## Bridge settings (Elfin EW11 and similar)

| Setting | Value |
|---|---|
| Serial: baud, data bits, parity, stop bits | Exactly what the bus uses (for example 115200 8N1) |
| Flow control | Half duplex (RS485) |
| Protocol | **None** (transparent), *not* Modbus |
| Route | UART |
| Socket | TCP server, port 8899 |
| Gap time | 10 ms works well |

Many bridges accept only one TCP client, so close any other tools connected
to the port.

### If you get no sensors

Check the **Frames decoded** and **Bytes discarded** status sensors:

- **Nothing received at all**: wiring or IP/port problem.
- **Lots of discarded bytes, no frames**: the bridge does not decode the bus.
  The two usual causes are:
  - **A and B swapped.** RS485 vendors label A/B inconsistently. Swapping the
    two data wires is harmless; try it first.
  - **Wrong baud rate.** Try 9600, 19200, 38400, 57600 and 115200 (8N1). Save
    *and reboot* the bridge after each change.
- Connect the signal ground (GND) between the bus and the bridge if one is
  available.

## Register map

**Settings → Devices & services → Modbus Sniffer → Configure.** The map is a
YAML list:

```yaml
- name: Grid voltage
  address: 37            # register number (decimal, or 0x25)
  table: input           # input (default), holding, coil or discrete
  slave: 1               # default 1
  data_type: uint16      # uint16 (default), int16, uint32, int32,
                         # uint32_swap, int32_swap, string
  scale: 0.1             # value = raw * scale + offset
  offset: 0
  precision: 1
  unit_of_measurement: V
  device_class: voltage
  state_class: measurement
- name: Battery power
  address: 40
  data_type: int16
  unit_of_measurement: W
  device_class: power
  state_class: measurement
- name: Energy exported
  address: 120
  data_type: uint32      # two registers, high word first
  scale: 0.1
  unit_of_measurement: kWh
  device_class: energy
  state_class: total_increasing
- name: Model
  address: 144
  data_type: string
  count: 8               # registers (2 characters each)
```

`examples/` contains starting points for specific devices.

## Finding out what registers mean

- Enable a few **raw sensors** and compare their history with the vendor app
  or the device's display.
- **Download diagnostics** (integration page → three dots) for a table of
  every register with hints such as *mains voltage x0.1 V?*, *probably
  signed*, *only increases (counter?)* and text strings found on the bus.
  Diagnostics can include serial numbers read from your devices, so check
  before sharing them.

## Limitations

- Passive only: it cannot read registers the existing master doesn't poll.
- Modbus RTU only (not Modbus ASCII or TCP framing on the bus).
- One bridge per config entry; add the integration again for more buses.

## License

MIT
