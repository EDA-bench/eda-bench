Build a complete KiCad project for `mowi` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/mowi.kicad_pro`
- `/workspace/final_project/mowi.kicad_sch`
- `/workspace/final_project/mowi.kicad_pcb`

Design objective

Design a six-layer integration board with USB input, protected power, USB hub distribution, wireless controller, Ethernet interfaces, UART bridging, and mixed external I/O.

Board constraints

- Use a six-layer board with an approximately 68.9 mm by 47.5 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Implement protected USB power entry, eFuse control, 3.3 V regulation, rail monitoring, and distributed decoupling.
- Connect the wireless controller and UART bridge to programming, debug, GPIO, I2C, and serial interfaces.
- Distribute USB through a two-port hub to the required modules and external connections.
- Implement both Ethernet interface paths, external connectors, antenna clearance, level translation, and all required module sideband signals.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- ESP32-class wireless controller
- USB2512B USB hub
- Two KSZ8041 Ethernet PHYs
- UART bridge and level translators
- eFuse and 3.3 V regulator

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
