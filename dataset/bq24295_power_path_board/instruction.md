Build a complete KiCad project for `bq24295_power_path_board` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/bq24295_power_path_board.kicad_pro`
- `/workspace/final_project/bq24295_power_path_board.kicad_sch`
- `/workspace/final_project/bq24295_power_path_board.kicad_pcb`

Design objective

Design a battery charger and power-path board that accepts USB-C or header power, charges a single-cell battery, supplies a regulated USB output, and exposes control and status signals.

Board constraints

- Use a two-layer board with an approximately 38 mm by 54 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect USB-C and auxiliary input power to the charger with current limiting, input decoupling, and the required configuration network.
- Provide a single-cell battery connector, battery monitoring, system output, and a switched 5 V USB-A output.
- Expose I2C, interrupt, status, enable, and power-path signals through two easyC connectors and breakout headers.
- Include jumper-selectable charger options, protection devices, and labeled test points for input, battery, system, 5 V, and ground.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- BQ24295_RGET charger and power-path controller
- Dual N-channel MOSFET
- USB-C receptacle
- USB-A receptacle
- Two easyC connectors

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
