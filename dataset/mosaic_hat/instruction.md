Build a complete KiCad project for `mosaic_hat` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/mosaic_hat.kicad_pro`
- `/workspace/final_project/mosaic_hat.kicad_sch`
- `/workspace/final_project/mosaic_hat.kicad_pcb`

Design objective

Design a Raspberry Pi HAT around a mosaic-X5 GNSS module with dual antenna inputs, USB connectivity, buffered host signals, and regulated power.

Board constraints

- Use a four-layer board with an approximately 65 mm by 56.5 mm Raspberry Pi HAT outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect the Raspberry Pi HAT header to the GNSS module through the required UART, GPIO, timing, control, power, and ground signals.
- Provide a USB Micro data path to the module with protection and correct differential routing.
- Route both RF antenna inputs with short controlled-impedance traces and connector keepouts.
- Implement regulated module power, signal buffering or level translation, status indicators, and the HAT mechanical mounting pattern.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- mosaic-X5 GNSS module
- Raspberry Pi HAT header
- USB Micro receptacle
- Two coaxial antenna connectors
- LD1117 regulator and SN74-series buffers

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
