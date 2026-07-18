Build a complete KiCad project for `logic_level_converter_board` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/logic_level_converter_board.kicad_pro`
- `/workspace/final_project/logic_level_converter_board.kicad_sch`
- `/workspace/final_project/logic_level_converter_board.kicad_pcb`

Design objective

Design a compact bidirectional level converter between low-voltage and high-voltage logic domains.

Board constraints

- Use a two-layer board with an approximately 22 mm by 22 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Provide separate low-side and high-side supply pins and grounds on the two external headers.
- Translate four bidirectional open-drain or slow digital channels between the two voltage domains.
- Use one MOSFET and the appropriate pull-up network per channel.
- Label both voltage domains and all channel mappings clearly on the silkscreen.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- Four small-signal N-channel MOSFETs
- Two six-pin headers
- Pull-up resistor networks

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
