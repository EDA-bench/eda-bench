Build a complete KiCad project for `cm4_carrier_net` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/cm4_carrier_net.kicad_pro`
- `/workspace/final_project/cm4_carrier_net.kicad_sch`
- `/workspace/final_project/cm4_carrier_net.kicad_pcb`

Design objective

Design a compact Compute Module 4 carrier with USB-C power and data, Ethernet, microSD storage, GPIO breakout, and switched peripheral power.

Board constraints

- Use a four-layer board with an approximately 90 mm by 40 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect the CM4 interface to Ethernet, USB 2.0, microSD, GPIO, I2C, UART, and the required power and control signals.
- Implement USB-C sink configuration, USB data routing, ESD protection, and an OTG mode-selection control.
- Provide switched microSD power, eMMC or boot selection support, and accessible 5 V and 3.3 V rails.
- Route Ethernet and USB differential pairs with continuous return paths and place protection close to their connectors.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- Compute Module 4 board-to-board connectors
- USB-C receptacle
- RJ45 Ethernet connector
- microSD socket
- TPD2EUSB30 USB protection device

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
