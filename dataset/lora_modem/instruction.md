Build a complete KiCad project for `lora_modem` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/lora_modem.kicad_pro`
- `/workspace/final_project/lora_modem.kicad_sch`
- `/workspace/final_project/lora_modem.kicad_pcb`

Design objective

Design a compact STM32 modem board with LoRa radio, CAN, UART, serial flash, regulated power, programming access, and antenna connection.

Board constraints

- Use a two-layer board with an approximately 24 mm by 36 mm outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Accept the available power inputs through a diode-OR path and generate a clean 3.3 V rail.
- Connect the STM32 to the LoRa module and serial flash over SPI, with separate chip selects and required control lines.
- Provide a CAN transceiver path, UART connector, SWD header, boot controls, reset, and status indication.
- Keep the RF path short, provide a clear antenna keepout, and isolate noisy power and bus routing from the radio section.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- STM32F103CB microcontroller
- Ra-02 LoRa module
- W25X40 serial flash
- TJA1050 CAN transceiver
- SPX3819 3.3 V regulator

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
