Build a complete KiCad project for `cm4_baseboard` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/cm4_baseboard.kicad_pro`
- `/workspace/final_project/cm4_baseboard.kicad_sch`
- `/workspace/final_project/cm4_baseboard.kicad_pcb`

Design objective

Design a full-featured Compute Module 4 baseboard with power conversion, networking, storage, display, camera, USB, M.2, debug, and user-control interfaces.

Board constraints

- Use a six-layer board with an approximately 107 mm by 68 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect both CM4 board-to-board sockets and route the required GPIO, power, PCIe, USB, Ethernet, display, camera, and control signals.
- Provide protected power input, 5 V and 3.3 V regulation, power switching, enable control, and rail test points.
- Include Ethernet, M.2, microSD, HDMI or display, camera, USB-C, USB host, debug, and user-control connectors with their required sideband signals.
- Route high-speed differential pairs with matched lengths, continuous return paths, appropriate impedance geometry, and ESD protection at external ports.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- Two Hirose DF40 CM4 sockets
- AP62301 buck regulator
- AP22615 load switch
- TXB0104 level translator
- USB-C, Ethernet, M.2, microSD, display, and camera connectors

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
