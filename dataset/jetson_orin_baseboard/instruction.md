Build a complete KiCad project for `jetson_orin_baseboard` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/jetson_orin_baseboard.kicad_pro`
- `/workspace/final_project/jetson_orin_baseboard.kicad_sch`
- `/workspace/final_project/jetson_orin_baseboard.kicad_pcb`

Design objective

Design a dense Jetson Orin carrier with protected power, USB-C and USB 3, Ethernet, M.2, camera, display, storage, RTC, debug, and expansion interfaces.

Board constraints

- Use an eight-layer board with an approximately 120 mm by 60 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect the Jetson module interface to all required power, control, GPIO, camera, display, Ethernet, USB, PCIe, storage, and serial signals.
- Implement USB-C power negotiation, protected rail distribution, load switching, current limiting, and the required sequencing and enable controls.
- Provide M.2 sockets, Ethernet, USB ports, camera connectors, RTC battery, debug, fan, and other specified external interfaces.
- Route USB 3, PCIe, Ethernet, MIPI, and display pairs with controlled impedance, matched lengths, continuous reference planes, and connector-side ESD protection.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- Jetson Orin board-to-board connectors
- AP22615 load switches
- NTS0102 level translator
- SiC431 regulator
- TPS259474 eFuse and TPD-series ESD arrays

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
