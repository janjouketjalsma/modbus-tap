# Writes

Some pollers only read. Others also write: a clock, an export limit, a charge setting. Watching those writes tells you what the poller is doing to your devices, even when you can't see its own settings.

## The write history

**Configure → Writes** ([where's Configure?](finding-your-way.md#configure-the-settings-of-your-bus)) shows:

- **A table of write blocks:** each unit, table and range of registers the poller writes, how many times, how many different values, and when it last wrote. Registers in your register map are shown by name.
- **The latest changes:** when a block got new values, and how often the same values were written after that.

The history is kept across restarts and stays small on purpose:

- The same values written again and again count as one change, with a count and a time range.
- At most 50 changes are kept per block, and at most 100 blocks. The oldest go first.

Tick **Clear the history** to start afresh, for example after changing something on the poller.

## Working out what the writes do

1. Leave the history running for a day or two, ideally while things change: prices, sun, battery level.
2. Look at **the latest changes** and when they happened. Changes at fixed times point to a schedule; changes that follow prices or export point to steering.
3. Make a [recording](recordings.md) with reference sources around those moments. It logs every write next to your reference values, and **Suggest a register map** passes the writes to the AI too.
4. Name the registers you've worked out under **Sensors**, so their current values become sensors.

## Other ways to see writes

- **In your sensors:** a confirmed write updates the register right away, so a mapped sensor shows the new value without waiting for the next read.
- **As events:** turn on **Configure → Advanced → Fire an event for every write** to get a `modbus_tap_write` event per write, for automations.
- **In diagnostics:** registers the poller wrote are marked "written by the poller".

## Writing yourself

Modbus Tap only listens; it never writes ([why](adr/0001-passive-only.md)). If you want to change settings yourself, keep in mind:

- **Two pollers on one bus collide.** RS485 lets one device talk at a time; a second one sending frames whenever it likes corrupts both.
- **The poller may undo your changes** the next time it writes.
- **Some registers are safety settings,** such as grid protection and battery limits. Only write registers whose meaning you're sure of.
- **Check who manages the poller.** If an installer or energy supplier runs it, ask them before working around it.

The clean way is to replace the poller: take it off the bus and let Home Assistant's core Modbus integration poll and write instead ([Replacing your poller](replacing-your-poller.md)).
