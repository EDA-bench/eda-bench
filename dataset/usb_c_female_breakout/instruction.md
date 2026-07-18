Build a complete KiCad project for `usb_c_female_breakout` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/usb_c_female_breakout.kicad_pro`
- `/workspace/final_project/usb_c_female_breakout.kicad_sch`
- `/workspace/final_project/usb_c_female_breakout.kicad_pcb`

Design objective

Design a simple USB-C receptacle breakout that exposes power, USB 2.0 data, configuration-channel, and sideband signals on a header.

Board constraints

- Use a two-layer board with an approximately 22 mm by 22 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Tie duplicate USB-C receptacle pins together where the connector orientation requires it.
- Route VBUS, ground, D+, D-, CC1, CC2, SBU1, and SBU2 to the corresponding header pins.
- Use short, symmetric USB data routing and adequate copper width for VBUS and ground.
- Label every header signal and provide a continuous board outline with connector mounting support.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- USB-C USB 2.0 receptacle
- Eight-pin breakout header

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
