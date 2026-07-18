Build a complete KiCad project for `asac_fc_rev_b` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/asac_fc_rev_b.kicad_pro`
- `/workspace/final_project/asac_fc_rev_b.kicad_sch`
- `/workspace/final_project/asac_fc_rev_b.kicad_pcb`

Design objective

Design a compact RP2040 flight controller with USB-C, inertial sensing, flash storage, regulated battery power, debug access, and external motor-control and serial interfaces.

Board constraints

- Use a four-layer board with an approximately 36 mm by 43 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Accept battery power and generate stable 5 V and 3.3 V rails with protection, bulk capacitance, and local decoupling.
- Provide USB-C sink configuration and USB 2.0 data connectivity to the RP2040.
- Connect the IMU and flash over SPI, and include the RP2040 crystal, reset, boot-selection, and SWD circuits.
- Expose the required ESC control outputs, UART channels, I2C, GPIO, power rails, and ground through clearly labeled headers.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- RP2040 microcontroller
- BMI270 inertial measurement unit
- W25Q128 serial flash
- 12 MHz crystal
- AMS1117 5 V and 3.3 V regulators

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
