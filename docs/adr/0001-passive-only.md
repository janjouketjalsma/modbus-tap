# Modbus Tap never transmits on the bus

Modbus Tap only listens: it never sends a byte to the **Bus**, not even optionally. Every bus it is meant for already has a **Poller**, and a second Modbus master would collide with it, which can break the vendor's own monitoring or control without either side noticing. Users who need registers the **Poller** never asks for should use Home Assistant's built-in Modbus integration instead, accepting that collision risk knowingly.

## Consequences

- Only **Registers** the **Poller** reads or writes are ever available, at the rate the **Poller** chooses.
- The **Bridge** connection is opened read-only in practice: the code has no write path to remove later, and tests assert that nothing is sent.
