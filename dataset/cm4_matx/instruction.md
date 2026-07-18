Build a complete KiCad project for `cm4_matx` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/cm4_matx.kicad_pro`
- `/workspace/final_project/cm4_matx.kicad_sch`
- `/workspace/final_project/cm4_matx.kicad_pcb`

Design objective

Design a Micro-ATX Compute Module 4 carrier with PCIe expansion, USB distribution, fan control, real-time clock support, and extensive external I/O.

Board constraints

- Use a four-layer 243.8 mm by 243.8 mm Micro-ATX board with standard mounting-hole placement.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect the CM4 power and control interface and distribute PCIe to three x16 mechanical slots with correct lane, clock, reset, and auxiliary power signals.
- Provide USB host distribution, switched port power, external USB connectors, headers, and protection.
- Include RTC, EEPROM, I2C expansion, fan control, debug, serial, storage, and general-purpose headers.
- Route high-speed pairs with controlled geometry and continuous return paths, and size all power paths for the slot and peripheral loads.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- Three PCIe x16 mechanical connectors
- MIC2019 USB power switches
- TCA9548 I2C multiplexer
- AP7363 regulator
- RTC and fan connectors

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
