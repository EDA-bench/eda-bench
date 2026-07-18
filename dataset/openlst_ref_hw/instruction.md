Build a complete KiCad project for `openlst_ref_hw` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/openlst_ref_hw.kicad_pro`
- `/workspace/final_project/openlst_ref_hw.kicad_sch`
- `/workspace/final_project/openlst_ref_hw.kicad_pcb`

Design objective

Design a sub-GHz telemetry board with an integrated radio microcontroller, RF power amplifier, antenna interface, regulated supplies, and programming and serial access.

Board constraints

- Use a four-layer board with an approximately 60 mm by 50 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Accept 5 V input and generate clean 3.3 V logic and 3.6 V RF rails with filtering and local decoupling.
- Connect the radio microcontroller to the RF front end, antenna matching network, transmit and receive control, and required clock circuitry.
- Provide programming, debug, UART, GPIO, reset, and power connectors.
- Keep the RF path compact, preserve a controlled-impedance antenna route, and isolate the RF supply and return currents from digital noise.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- CC1110 radio microcontroller
- RFFM6403 RF front-end module
- STA1120A RF switch or control device
- LM1117-3.3 and LT1086-3.6 regulators
- Antenna and debug connectors

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
