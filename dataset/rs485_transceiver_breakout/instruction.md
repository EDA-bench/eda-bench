Build a complete KiCad project for `rs485_transceiver_breakout` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/rs485_transceiver_breakout.kicad_pro`
- `/workspace/final_project/rs485_transceiver_breakout.kicad_sch`
- `/workspace/final_project/rs485_transceiver_breakout.kicad_pcb`

Design objective

Design a compact TTL-to-RS-485 transceiver board with bus termination, biasing, power routing, and clear external connections.

Board constraints

- Use a two-layer board with an approximately 38 mm by 22 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect TTL transmit, receive, driver-enable, and receiver-enable signals to the transceiver.
- Provide a three-pin differential bus terminal for A, B, and ground.
- Include selectable 120 ohm termination and the required fail-safe bias network.
- Expose power, ground, and logic signals on a labeled six-pin header and decouple the transceiver locally.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- SN65176B RS-485 transceiver
- Three-pin screw terminal
- Six-pin logic header
- Termination-selection jumper

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
