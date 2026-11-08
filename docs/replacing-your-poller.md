# Replacing your poller

Once your register map is complete, you may want Home Assistant to talk to the device itself, without the vendor dongle or logger. Modbus Tap's maps use the core Modbus format, so this is a short step.

> [!WARNING]
> Removing a vendor dongle can stop cloud monitoring, remote support and warranty reporting. Some devices also expect regular polling or writes from their logger. Check what you lose first.

## 1. Export

**Configure → Export to core Modbus** gives a ready-to-paste block:

```yaml
modbus:
  - name: modbus_tap_export
    type: rtuovertcp
    host: 192.168.1.120
    port: 8899
    sensors:
      - name: Grid voltage
        address: 37
        device_address: 1
        input_type: input
        scale: 0.1
        precision: 1
        scan_interval: 20
```

`scan_interval` is set to how often your old poller asked, so the device sees the same load. The `documented` and `verified` notes are left out, because core doesn't use them.

## 2. Look at what the poller wrote

The old poller may have done more than read. On a Sosen inverter, for example, an Elinter Magpie sets the inverter's clock. Check a recording for `transaction` lines with `function` 6 or 16 (or enable write events in Settings and watch `modbus_tap_write`). If something matters, recreate it with an automation that calls `modbus.write_register` from core Modbus.

## 3. Switch over

1. Unplug the old poller from the bus.
2. Keep the bridge in transparent mode. Core's `rtuovertcp` type speaks Modbus RTU through it.
3. Paste the export into `configuration.yaml` and restart Home Assistant.
4. Check the new core Modbus sensors against the Modbus Tap ones.

## 4. Modbus Tap afterwards

Remove the Modbus Tap integration, or keep it listening. Home Assistant is now the poller, so Modbus Tap will see its requests. That's handy for checking core's traffic, or for recording a register you add later. If you keep both, make sure the bridge accepts two clients.
