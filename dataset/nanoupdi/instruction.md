Build a complete KiCad project for `nanoupdi` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/nanoupdi.kicad_pro`
- `/workspace/final_project/nanoupdi.kicad_sch`
- `/workspace/final_project/nanoupdi.kicad_pcb`

Design objective

Design a small USB-C programmer that converts USB to UART or UPDI signaling and supports selectable target-voltage behavior.

Board constraints

- Use a two-layer board with an approximately 10 mm by 22 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Provide USB-C sink configuration, USB 2.0 routing, input protection, and power indication.
- Connect the USB bridge to a three-pin UPDI output with the required series or combining network.
- Implement target-power selection between USB-derived and externally supplied voltage modes.
- Expose the UPDI signal, target voltage, and ground with clear connector labeling.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- CH340E USB-to-UART bridge
- AP2112K-3.3 regulator
- USB-C receptacle
- Three-pin UPDI connector
- Power-selection switch

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
