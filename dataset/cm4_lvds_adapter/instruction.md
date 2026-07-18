Build a complete KiCad project for `cm4_lvds_adapter` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/cm4_lvds_adapter.kicad_pro`
- `/workspace/final_project/cm4_lvds_adapter.kicad_sch`
- `/workspace/final_project/cm4_lvds_adapter.kicad_pcb`

Design objective

Design a Compute Module display adapter that converts MIPI DSI to LVDS and generates the display bias and logic rails required by an attached panel.

Board constraints

- Use a six-layer board with an approximately 52 mm by 43 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Route the CM4 MIPI DSI lanes to the bridge with controlled differential geometry and continuous reference planes.
- Connect the LVDS output pairs, display control signals, I2C configuration bus, and FFC sideband signals to the panel connectors.
- Generate the required display rails and bias voltages with sequencing, filtering, feedback networks, and local decoupling.
- Provide level translation where required and place high-speed bridge and connector components to minimize pair length and crossings.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- SN65DSI84 MIPI DSI-to-LVDS bridge
- TPS65150 display bias supply
- NTS0104 level translator
- TLV-series regulators
- CM4, LVDS, and FFC connectors

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
