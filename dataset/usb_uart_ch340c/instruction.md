Build a complete KiCad project for `usb_uart_ch340c` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/usb_uart_ch340c.kicad_pro`
- `/workspace/final_project/usb_uart_ch340c.kicad_sch`
- `/workspace/final_project/usb_uart_ch340c.kicad_pcb`

Design objective

Design a compact USB-C serial adapter with regulated power, UART breakout, FTDI-style header mapping, and selectable configuration behavior.

Board constraints

- Use a two-layer board with an approximately 38 mm by 22 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Provide USB-C sink configuration, protected USB 2.0 routing, input fuse protection, and local decoupling.
- Connect the CH340C UART, modem-control, and status signals to the external headers.
- Provide both a standard UART breakout and an FTDI-style six-pin header with power and ground.
- Implement the required voltage or routing selection switch and jumper behavior, with clear silkscreen labels.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- CH340C USB-to-UART bridge
- SE5218 regulator
- USB-C receptacle
- Resettable fuse
- UART and FTDI-style headers

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
