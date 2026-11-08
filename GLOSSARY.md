# Modbus Tap

Modbus Tap listens to an existing Modbus bus and turns the values that pass by into Home Assistant sensors, without ever taking part in the conversation.

## Language

### On the bus

**Bus**:
One shared serial line (typically RS485) and everything connected to it.
_Avoid_: Network, line, port

**Poller**:
A device already on the **Bus** that sends requests, such as a vendor data logger or dongle.
_Avoid_: Master, client, logger

**Unit**:
A device on the **Bus** that answers requests, identified by its **Unit address**.
_Avoid_: Slave, server, device

**Unit address**:
The number (0-247) that identifies a **Unit** on its **Bus**.
_Avoid_: Slave ID, device ID, station number

**Register**:
One 16-bit value at an address in one of a **Unit**'s register tables (holding, input, coil or discrete input).
_Avoid_: Point, tag, data point

**Transaction**:
One request from the **Poller** together with the **Unit**'s matching response.
_Avoid_: Exchange, poll, message

**Write**:
A **Transaction** in which the **Poller** changes one or more **Registers** of a **Unit**. It is _confirmed_ when the **Unit** echoes it back, _rejected_ when the **Unit** answers with an exception, and _unanswered_ when no response follows.
_Avoid_: Command, set

### Listening

**Tap**:
The act of listening to a **Bus** without transmitting on it, and the name of this project.
_Avoid_: Sniffer, hub, gateway

**Bridge**:
The device that forwards every byte heard on the **Bus** to Home Assistant over the network, such as an Elfin EW11 in transparent mode.
_Avoid_: Gateway, converter, adapter

**Tap cable**:
A cable that adds a branch to an existing **Bus** connection so a **Bridge** can listen in, often made from an extension cable.
_Avoid_: Splitter, Y-cable, sniffer cable

**Recording**:
A time-stamped log of every decoded **Transaction** on a **Bus**, started and stopped by the user, used to work out what **Registers** mean.
_Avoid_: Capture, dump, trace

### Meaning

**Register map**:
Definitions that give **Registers** a name, data type, scale and unit, so they can become meaningful sensors.
_Avoid_: Register list, profile, definition file

**Community map**:
A **Register map** for a specific make and model, shipped with Modbus Tap and maintained by its users.
_Avoid_: Built-in map, template, preset

**Override**:
A user's own entry that replaces or adds to an entry of the **Community map** it is based on, matched by **Unit address**, table and address.
_Avoid_: Patch, customisation

**Documented**:
A **Register map** entry whose meaning comes from a written source, such as the manufacturer's protocol document.
_Avoid_: Official, specified

**Verified**:
A **Register map** entry that someone has checked against a real device, recorded with that device's model and firmware.
_Avoid_: Tested, confirmed

**Guessed**:
A **Register map** entry that is neither **Documented** nor **Verified**, typically inferred from bus traffic.
_Avoid_: Unverified, inferred, unknown
