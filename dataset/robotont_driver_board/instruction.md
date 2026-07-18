Build a complete KiCad project for `robotont_driver_board` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/robotont_driver_board.kicad_pro`
- `/workspace/final_project/robotont_driver_board.kicad_sch`
- `/workspace/final_project/robotont_driver_board.kicad_pcb`

Design objective

Design a motor driver board with an H-bridge power stage, isolated controller interface, encoder connection, local regulation, sensing, and protection.

Board constraints

- Use a two-layer board with an approximately 40 mm by 55.1 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Accept motor power through a protected input connector and distribute it to the H-bridge and local regulator.
- Connect the isolated controller interface to direction, enable, PWM, fault, and sensing signals.
- Provide a motor output connector and an encoder connector with the required power and signal routing.
- Implement current handling, flyback and transient protection, local decoupling, thermal copper, and clearly separated power and logic return paths.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- MC33887 H-bridge motor driver
- Si8641 digital isolator
- MIC5205 regulator
- Power MOSFET and protection network
- Motor, encoder, power, and controller connectors

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
