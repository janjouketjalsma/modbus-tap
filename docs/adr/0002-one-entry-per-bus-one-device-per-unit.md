# One config entry per bus, one device per unit

A Home Assistant config entry represents one **Bus**, reached through one **Bridge**. Each **Unit address** seen on that **Bus** becomes its own Home Assistant device, linked "via" a separate device for the **Bridge**, which only carries connection and decoding health. We chose this over one device per **Bridge** because users think in terms of their inverter or meter, not the cable it hangs off, and over one config entry per **Unit** because a single **Bridge** connection carries every **Unit** on the **Bus**.

## Consequences

- Entity and device identifiers are derived from the **Unit address**, so changing this structure later would orphan users' entities, history and dashboards.
- A new **Unit** appearing on the **Bus** gets a new device automatically.
