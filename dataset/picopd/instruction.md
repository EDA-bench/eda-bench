Build a complete KiCad project for `picopd` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/picopd.kicad_pro`
- `/workspace/final_project/picopd.kicad_sch`
- `/workspace/final_project/picopd.kicad_pcb`

Design objective

Design a Pico-format RP2040 development board with USB-C power negotiation, external flash, debug access, and switched VBUS distribution.

Board constraints

- Use a four-layer board with an approximately 20.6 mm by 51.1 mm Pico-compatible outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect USB-C CC and power signals to the power-delivery controller and implement the required sink configuration, protection, and filtering.
- Connect USB 2.0 data, external flash, the 12 MHz clock, boot, reset, and SWD circuits to the RP2040.
- Generate a stable 3.3 V rail and route negotiated or switched VBUS to the specified Pico-style header pins.
- Expose GPIO, ADC, serial buses, power, and ground through two Pico-compatible header rows.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- RP2040 microcontroller
- AP33772 USB power-delivery controller
- AP2204K-3.3 regulator
- W25Q16 serial flash
- USB-C receptacle

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
