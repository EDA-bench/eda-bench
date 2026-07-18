Build a complete KiCad project for `m2_pcie_adapter` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/m2_pcie_adapter.kicad_pro`
- `/workspace/final_project/m2_pcie_adapter.kicad_sch`
- `/workspace/final_project/m2_pcie_adapter.kicad_pcb`

Design objective

Design a passive adapter that maps a PCIe x4 connector to an M.2 Key-M edge interface and supplies the required auxiliary power.

Board constraints

- Use a four-layer board with an approximately 80 mm by 33.7 mm outline and the required card-retention features.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Map four PCIe transmit and receive lanes with correct polarity and lane ordering.
- Route the reference clock, reset, wake, clock-request, SMBus, presence, and sideband signals required by the two interfaces.
- Distribute auxiliary power and ground with appropriate bulk and high-frequency decoupling.
- Use controlled differential geometry, matched intra-pair lengths, continuous reference planes, and minimal layer transitions.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- PCIe x4 connector
- M.2 Key-M edge interface
- Auxiliary power header
- M.2 retention hardware

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
