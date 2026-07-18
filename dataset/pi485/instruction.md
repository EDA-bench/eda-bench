Build a complete KiCad project for `pi485` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/pi485.kicad_pro`
- `/workspace/final_project/pi485.kicad_sch`
- `/workspace/final_project/pi485.kicad_pcb`

Design objective

Design a discrete UART-to-RS-485 interface with automatic direction control, bus termination, biasing, and host connectivity.

Board constraints

- Use a two-layer board with an approximately 63 mm by 46 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect host UART transmit and receive signals to the RS-485 transceiver.
- Implement automatic transmit-enable timing around an NE555 and complementary transistor control stage.
- Provide the differential bus connector, selectable 120 ohm termination, bias resistors, and transient protection.
- Expose host power, ground, UART, and optional control signals on a labeled header.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- MAX485 transceiver
- NE555 timer
- 2N3904 and 2N3906 transistors
- Raspberry Pi or UART header
- RS-485 screw terminal

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
