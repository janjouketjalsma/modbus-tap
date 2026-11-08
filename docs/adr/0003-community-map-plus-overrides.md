# Community maps are used as a base with user overrides on top

A **Bus** can use a **Community map** as its base, and the user's own entries act as **Overrides** matched by **Unit address**, table and address, instead of the user getting an editable copy. Community maps are often partly wrong or incomplete for a given firmware, so users need to correct them locally, but a copy would freeze them on the version they started from and they would never receive later community fixes. Users who want full control can still copy a community map into their own map and drop the base.

## Consequences

- Stored configuration holds a reference to the community map plus only the user's differences, so the community map format and entry keys are effectively a public contract.
