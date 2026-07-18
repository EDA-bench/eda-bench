Build a complete KiCad project for `rp2040_dmxsun_ioboard` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/rp2040_dmxsun_ioboard.kicad_pro`
- `/workspace/final_project/rp2040_dmxsun_ioboard.kicad_sch`
- `/workspace/final_project/rp2040_dmxsun_ioboard.kicad_pcb`

Design objective

Design an RP2040-compatible DMX interface board with two transceiver channels, XLR and modular connectors, EEPROM, regulated power, and a backplane interface.

Board constraints

- Use a two-layer board with an approximately 106 mm by 55 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Implement two RS-485 or DMX transceiver channels with direction control, termination, biasing, and protection.
- Route the DMX buses to four XLR connectors and two 8P8C connectors with consistent pin mapping.
- Provide the modular backplane connection for control, I2C, power, ground, and channel signals.
- Include identification EEPROM, 3.3 V regulation, decoupling, status indication, and labeled power inputs.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- Two SP3485 transceivers
- Four three-pin XLR connectors
- Two 8P8C connectors
- M24C64 EEPROM
- AMS1117-3.3 regulator

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
