Build a complete KiCad project for `gimme_danger` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/gimme_danger.kicad_pro`
- `/workspace/final_project/gimme_danger.kicad_sch`
- `/workspace/final_project/gimme_danger.kicad_pcb`

Design objective

Design a compact ESP32-S3 control board with USB-C input, current sensing, I2C and UART connectivity, and four protected low-side output channels.

Board constraints

- Use a four-layer board with an approximately 48 mm by 42 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Accept USB-C power and generate a stable 3.3 V rail with protection, bulk capacitance, and local decoupling.
- Provide USB, UART, I2C, boot, reset, and programming connectivity for the ESP32-S3.
- Implement four low-side MOSFET output channels with gate control, load connectors, and protection appropriate for external loads.
- Measure input or load current and expose the required sensed values and control signals through the external interface.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- ESP32-S3 module
- Four AO3400 N-channel MOSFETs
- INA219 current monitor
- FUSB302 USB-C controller
- TPS54302 buck regulator

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
