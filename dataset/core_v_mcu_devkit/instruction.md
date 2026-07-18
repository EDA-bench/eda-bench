Build a complete KiCad project for `core_v_mcu_devkit` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/core_v_mcu_devkit.kicad_pro`
- `/workspace/final_project/core_v_mcu_devkit.kicad_sch`
- `/workspace/final_project/core_v_mcu_devkit.kicad_pcb`

Design objective

Design a microcontroller development board with USB-C power and data, multi-channel debug, voltage-domain translation, camera, mikroBUS, and general expansion interfaces.

Board constraints

- Use a four-layer board with an approximately 100 mm by 75 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Provide USB-C power and data to a dual-channel USB bridge with configuration EEPROM, clocking, protection, and status indication.
- Implement the programming and debug paths, translated I/O banks, camera connector, mikroBUS socket, and general-purpose headers.
- Generate the required core and I/O rails with current limiting, decoupling, and accessible power-selection points.
- Route USB and camera signals with appropriate differential geometry and keep voltage translators close to the interfaces they serve.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- FT2232HL dual USB bridge
- NTB0104 level translators
- MP6400 power switches
- AP2127K regulator
- Camera, mikroBUS, debug, and expansion connectors

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
