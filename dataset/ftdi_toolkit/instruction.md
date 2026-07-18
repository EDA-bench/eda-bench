Build a complete KiCad project for `ftdi_toolkit` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/ftdi_toolkit.kicad_pro`
- `/workspace/final_project/ftdi_toolkit.kicad_sch`
- `/workspace/final_project/ftdi_toolkit.kicad_pcb`

Design objective

Design a compact USB-C debug and protocol adapter with selectable I/O voltage domains and multiple buffered FTDI channel breakouts.

Board constraints

- Use a four-layer board with an approximately 53 mm by 20.1 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Provide USB-C power and data entry with CC resistors, protection, filtering, and a stable local rail.
- Expose UART, debug, protocol, and general-purpose FTDI channel signals through labeled headers.
- Support selectable external I/O voltage domains and translate signals in both directions as required.
- Place translators and multiplexers close to the headers, provide local decoupling, and keep the USB pair short and matched.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- USB-C receptacle
- SN74LVC1T45 single-bit translators
- 74LVC2T45 dual-bit translators
- TS5A3359 analog switches
- MOSFET power and signal switches

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
