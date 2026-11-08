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

### Listening

**Tap**:
The act of listening to a **Bus** without transmitting on it, and the name of this project.
_Avoid_: Sniffer, hub, gateway

**Bridge**:
The device that forwards every byte heard on the **Bus** to Home Assistant over the network, such as an Elfin EW11 in transparent mode.
_Avoid_: Gateway, converter, adapter

**Register map**:
Definitions that give **Registers** a name, data type, scale and unit, so they can become meaningful sensors.
_Avoid_: Register list, profile, definition file
