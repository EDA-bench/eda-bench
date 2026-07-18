Build a complete KiCad project for `cm4_csi_adapter` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/cm4_csi_adapter.kicad_pro`
- `/workspace/final_project/cm4_csi_adapter.kicad_sch`
- `/workspace/final_project/cm4_csi_adapter.kicad_pcb`

Design objective

Design a passive adapter that maps a Compute Module camera interface to a camera FFC connector while preserving four-lane MIPI CSI signaling and sideband control.

Board constraints

- Use a four-layer board with an approximately 47 mm by 33 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Route four MIPI CSI data lanes and the clock pair between the two connectors with correct polarity and lane mapping.
- Route 3.3 V, ground, I2C, camera control, and other required sideband signals between the connectors.
- Use length matching, differential-pair spacing, continuous reference planes, minimal vias, and short pair breakouts.
- Include the specified connector mounting and board mounting features within the stated outline.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- Würth Elektronik 68715014522 high-density connector
- Würth Elektronik 687122149022 FFC connector
- Mechanical mounting holes

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
