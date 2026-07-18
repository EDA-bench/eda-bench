Build a complete KiCad project for `adau1452_dsp_core` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/adau1452_dsp_core.kicad_pro`
- `/workspace/final_project/adau1452_dsp_core.kicad_sch`
- `/workspace/final_project/adau1452_dsp_core.kicad_pcb`

Design objective

Design a self-contained digital audio processing core around the ADAU1452, with boot memory, clock distribution, regulated supplies, control access, and digital audio expansion.

Board constraints

- Use a four-layer board with an approximately 100 mm by 100 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Accept the main power input and generate clean 3.3 V and 1.2 V rails with appropriate filtering, sequencing, decoupling, and test access.
- Connect an external EEPROM for self-boot and expose the DSP SPI control signals through a dedicated control header.
- Provide digital audio input and output headers, clock and synchronization signals, GPIO, UART, I2C, reset, and debug access.
- Route digital audio clocks and data with controlled return paths and keep the clock distribution section compact.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- ADAU1452WBCPZ audio DSP
- 24M576 serial EEPROM
- ADP2301AUJZ regulator
- NB3L553 clock fanout buffer
- S/PDIF optical receiver and transmitter modules

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
