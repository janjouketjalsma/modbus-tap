# Tapping your bus

How to get a network bridge listening to an RS485 Modbus bus that's already in use: find the right pins, build a tap cable, wire the bridge and get clean frames.

> [!WARNING]
> **Read this first.** Inverters, batteries and their surroundings carry voltages that can kill: hundreds of volts DC from solar panels, high-current battery circuits and mains AC. Everything in this guide is about the **low-voltage communication port only**.
>
> - Never open the inverter or any other enclosure. If the port is inside, ask your installer.
> - Never connect anything to a pin you haven't identified. Measure first.
> - Changing cables or connectors may affect your warranty.
> - You do this at your own risk. The authors of Modbus Tap accept no responsibility for damage, injury or lost warranty.

## What you need

- A **network RS485 bridge** that can forward raw bytes over TCP ("transparent" mode). An Elfin EW11 works well. An ESP32 with an RS485 module running a TCP serial-stream firmware also works.
- A **multimeter**. A cheap one is fine.
- An **extension cable** for the connector your port uses, or a matching plug and some cable.
- Optional: a **100 Ω resistor** for the signal ground (see [Ground](#ground)).

## 1. Find the pins

A typical RS485 port on an inverter or logger socket has four wires: power, ground and the two data lines, A and B. Find out which is which before connecting anything.

With everything running normally (the existing logger or dongle plugged in, so the bus is active), measure DC voltage between pairs of pins:

1. **Find ground and power.** Look for the pair with the biggest steady voltage between them, typically 5 V or 12 V. The higher pin is power, the lower one is ground.
2. **Measure the other two pins against ground.** RS485 data lines idle around 2 to 3 V, close together, for example 2.6 V and 2.2 V.
3. **Measure between the two data pins.** Expect a few tenths of a volt (for example 0.38 V). Write down which pin reads higher at idle.
4. **Watch the numbers flicker.** When the logger polls, the data pins wobble a little on the display. A multimeter is too slow to show the bits, but movement is a good sign there's traffic.

Never connect the power pin to your bridge's data terminals. Powering the bridge from it is possible, but only if you know the bridge's input range and that the port can supply the current. When in doubt, use the bridge's own power adapter.

## 2. Build a tap cable

You want the existing device and the bridge on the same four wires, without cutting the original cable.

- **Use an extension cable** for your port's connector. Plug it between the port and the existing logger, so the logger keeps working.
- **Tap into it:** carefully open the outer sheath in the middle, and splice two wires (data A and data B), plus optionally ground, out to the bridge. Solder and insulate each joint, or use proper splice connectors.
- **Keep the tap short**, ideally under a metre, and keep the two data wires twisted together.
- **Label the wires** with the pin roles you measured. You'll thank yourself later.

## 3. Wire the bridge

| Bus | Bridge terminal |
|---|---|
| Data line that idles **higher** | Usually **B** (on bridges that follow the RS485 standard's naming) |
| Data line that idles **lower** | Usually **A** |
| Ground | GND, ideally through a 100 Ω resistor |
| Power | Leave unconnected |

RS485 vendors label A and B inconsistently, so treat the table as a starting point. If nothing decodes, swap the two data wires. That's harmless.

### Ground

RS485 is differential, so it often works without a ground wire. If you see garbled data, connect the bus ground to the bridge's GND. First measure the voltage between the two grounds with the multimeter, both DC and AC. Connect them only if both readings are small: under 1 V DC and under about 10 V AC. A 100 Ω resistor in the ground wire limits any current if the grounds differ.

### Termination

Leave termination resistors out. The bus already has its terminations at its ends, and your tap is a short branch.

## 4. Set up the bridge

| Setting | Value |
|---|---|
| Baud rate, data bits, parity, stop bits | What the bus uses. 9600 8N1 is common, but don't assume it (see below) |
| Flow control | Half duplex (RS485) |
| Protocol | **None** (transparent) |
| Route | UART |
| Socket | TCP server, port 8899 |
| Gap time | 10 ms |

**Save and reboot the bridge after every change.** Some bridges only apply serial settings after a reboot.

If anything else also connects to the bridge, make sure it accepts more than one client (on Elfin devices: socket "max accept" of 2 or more).

### Finding the baud rate

If you don't know the bus speed, try 9600, 19200, 38400, 57600 and 115200 at 8N1, and check each with Modbus Tap's **Frames decoded** sensor. A wrong baud rate gives plenty of bytes but zero frames. On Elfin devices you can also switch **Route** to **Log** for a minute. The log shows how the bridge splits traffic into frames, and at the right speed you'll see regular 8-byte requests followed by longer replies.

## 5. Add Modbus Tap

Add the integration, enter the bridge's IP address and port, and check the bridge device in Home Assistant:

- **Connection** shows *Connected*.
- **Frames decoded** climbs every time your logger polls.
- **Bytes discarded** stays low.

## Troubleshooting

Modbus Tap raises a repair in Home Assistant when it recognises one of these patterns.

| What you see | Likely cause | Try |
|---|---|---|
| Connected, but no bytes at all | The bridge isn't on the bus | Check the splice and terminals. Across the bridge's A and B you should measure the same few tenths of a volt as on the port. About 3 V means it isn't connected to the bus. |
| Many bytes, zero frames, lots of zero bytes | A and B swapped | Swap the two data wires |
| Many bytes, zero frames, mostly other junk | Wrong baud rate or parity | Go through the baud rates above, rebooting the bridge each time. Then try swapping A and B. |
| Frames decode but some are garbled | Weak signal or noise | Shorten the tap, twist the data pair, connect ground |
| Bridge connection fails | Address, or the bridge refuses another client | Check the IP and port, and the bridge's client limit |
| The existing logger stopped working | Your wiring interferes with the bus | Disconnect the tap at once and recheck the pin mapping |

## Next

Your bus is decoding? Give the registers names: [Register maps](register-maps.md). No documentation for your device? [Working out a register map](working-out-a-register-map.md).
