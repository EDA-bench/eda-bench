Build a complete KiCad project for `zynq_som` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/zynq_som.kicad_pro`
- `/workspace/final_project/zynq_som.kicad_sch`
- `/workspace/final_project/zynq_som.kicad_pcb`

Design objective

Design a dense Zynq-7000 system-on-module with DDR3 memory, boot flash, Ethernet, USB, clocks, power conversion, sensing, debug, and high-density carrier connectors.

Board constraints

- Use an eight-layer board with an approximately 50 mm by 42 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect the Zynq processing system and programmable logic banks to DDR3, boot flash, Ethernet PHY, USB, debug, clocks, and the carrier connectors.
- Generate and sequence all required core, auxiliary, I/O, memory, Ethernet, and peripheral rails with adequate current capacity and decoupling.
- Route DDR3 address, command, clock, data, and strobe groups with controlled geometry and appropriate length matching.
- Route Ethernet, USB, and other high-speed pairs with continuous return planes, and expose all specified GPIO, power, storage, and control signals through the three high-density connectors.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- XC7Z020 Zynq-7000 SoC
- MT41K-series DDR3 memory
- W25Q128 boot flash
- RTL8211F Ethernet PHY
- STM32G431, BMI323, MPM regulators, and three DF40 connectors

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
