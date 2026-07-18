Build a complete KiCad project for `quanta75_pico` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/quanta75_pico.kicad_pro`
- `/workspace/final_project/quanta75_pico.kicad_sch`
- `/workspace/final_project/quanta75_pico.kicad_pcb`

Design objective

Design a 75 percent keyboard PCB with a Pico-format controller, full key matrix, rotary encoder, USB hub, upstream USB-C, downstream USB, and expansion headers.

Board constraints

- Use a two-layer board with an approximately 317.5 mm by 163.5 mm keyboard outline and mounting features appropriate for a 75 percent layout.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Implement the complete 82-switch key matrix with one diode per switch, row and column routing, and a rotary encoder.
- Provide a Pico-format controller socket with all matrix, encoder, USB, power, and expansion signals connected.
- Connect an upstream USB-C port to a USB hub and route the required downstream USB-C and USB-A ports with protected power distribution.
- Include exposed GPIO and power headers, board mounting holes, switch footprints, stabilizer clearances, and clear switch and connector labels.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- 82 mechanical key switches and diodes
- SL2.1A USB hub
- Two USB-C receptacles
- Two USB-A receptacles
- Pico-format controller headers and rotary encoder

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
