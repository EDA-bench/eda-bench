Build a complete KiCad project for `mcp23017_breakout` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/mcp23017_breakout.kicad_pro`
- `/workspace/final_project/mcp23017_breakout.kicad_sch`
- `/workspace/final_project/mcp23017_breakout.kicad_pcb`

Design objective

Design a compact I2C GPIO expander board with sixteen GPIO signals, address selection, reset, interrupt outputs, and chainable power and bus connectors.

Board constraints

- Use a two-layer board with an approximately 22 mm by 38 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect both MCP23017 GPIO banks to labeled breakout headers.
- Provide two easyC I2C connectors, bus pull-ups, power, ground, reset, and both interrupt outputs.
- Include selectable address inputs and a local regulated or protected supply path as required.
- Place decoupling close to the expander and regulator and label every address and GPIO signal.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- MCP23017 GPIO expander
- SE5218 regulator
- Two small-signal MOSFETs
- Two easyC connectors
- GPIO breakout headers

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
