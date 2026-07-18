Build a complete KiCad project for `mitayi_pico_d1` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/mitayi_pico_d1.kicad_pro`
- `/workspace/final_project/mitayi_pico_d1.kicad_sch`
- `/workspace/final_project/mitayi_pico_d1.kicad_pcb`

Design objective

Design a narrow RP2040 development board with USB-C, external flash, regulated power, SWD, boot and reset controls, and complete GPIO breakout.

Board constraints

- Use a two-layer board with an approximately 51 mm by 21 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect USB-C power and USB 2.0 data to the RP2040 with sink resistors, protection, and correct differential routing.
- Provide the 12 MHz crystal network, external serial flash, boot-selection button, reset button, and SWD access.
- Generate a stable 3.3 V rail and implement the RP2040 core-supply filtering and decoupling requirements.
- Expose the required GPIO, ADC, power, ground, serial, SPI, and I2C signals through two labeled header rows.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- RP2040 microcontroller
- W25Q32 serial flash
- MIC5219-3.3 regulator
- 12 MHz crystal
- USB-C receptacle

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
