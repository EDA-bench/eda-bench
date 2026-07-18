Build a complete KiCad project for `ict_baseboard` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/ict_baseboard.kicad_pro`
- `/workspace/final_project/ict_baseboard.kicad_sch`
- `/workspace/final_project/ict_baseboard.kicad_pcb`

Design objective

Design a test baseboard with USB-C and barrel power, protected test-socket banks, analog acquisition, GPIO expansion, bus multiplexing, and user controls.

Board constraints

- Use a four-layer board with an approximately 150 mm by 50 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Accept USB-C and barrel power, select and regulate the required rails, and provide input and rail protection.
- Connect the test socket banks and side connector to protected GPIO, analog measurement, SPI, UART, I2C, power, and ground resources.
- Implement I2C GPIO expansion, analog-to-digital conversion, and bus multiplexing for the test interfaces.
- Include user switches, status indication, labeled test points, local decoupling, and robust ESD protection on exposed signals.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- PCA9539 GPIO expanders
- ADS7828 analog-to-digital converters
- TCA9548 I2C multiplexer
- TPD4E02 ESD arrays
- SiC431 power regulator

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
