Build a complete KiCad project for `m2_5g_usb3_interface` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/m2_5g_usb3_interface.kicad_pro`
- `/workspace/final_project/m2_5g_usb3_interface.kicad_sch`
- `/workspace/final_project/m2_5g_usb3_interface.kicad_pcb`

Design objective

Design a carrier for an M.2 cellular modem with 3.8 V power, USB 2 and USB 3 connectivity, dual SIM interfaces, reset and status controls, and debug access.

Board constraints

- Use a four-layer board with an approximately 90 mm by 40 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Accept barrel and USB power inputs and generate a high-current 3.8 V modem rail with protection, filtering, enable control, and test points.
- Connect the M.2 modem socket to USB 3 and USB 2 connectors with correct differential-pair mapping and sideband signals.
- Provide two SIM sockets with the required selection, power, clock, reset, and data routing.
- Expose modem reset, wake, status, UART, debug, and power-control signals through labeled headers or test points.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- 2199119-3 M.2 socket
- KUSBX USB 3 connector
- Two SIM sockets
- AP62301 regulator
- Barrel power connector

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
