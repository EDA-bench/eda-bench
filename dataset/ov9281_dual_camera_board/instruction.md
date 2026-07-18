Build a complete KiCad project for `ov9281_dual_camera_board` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/ov9281_dual_camera_board.kicad_pro`
- `/workspace/final_project/ov9281_dual_camera_board.kicad_sch`
- `/workspace/final_project/ov9281_dual_camera_board.kicad_pcb`

Design objective

Design a dual global-shutter camera board with two OV9281 sensors, separate clocks and regulated rails, shared control buses, and two high-speed camera interfaces.

Board constraints

- Use a four-layer board with an approximately 100 mm by 25 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect each image sensor to its camera connector with the required MIPI data and clock lanes, control signals, reset, and synchronization.
- Generate and distribute the 2.8 V, 1.8 V, and 1.2 V sensor rails with correct decoupling and sequencing support.
- Provide a 24 MHz clock for each sensor and route the I2C control bus with the required level translation.
- Route MIPI pairs with controlled geometry, matched lengths, continuous return planes, minimal vias, and proper sensor and connector placement.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- Two OV9281 image sensors
- Two 24 MHz crystals
- TLV733 2.8 V, 1.8 V, and 1.2 V regulators
- I2C level translators
- Two camera connectors and lens mounts

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
