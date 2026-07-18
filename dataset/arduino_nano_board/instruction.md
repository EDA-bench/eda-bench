Build a complete KiCad project for `arduino_nano_board` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/arduino_nano_board.kicad_pro`
- `/workspace/final_project/arduino_nano_board.kicad_sch`
- `/workspace/final_project/arduino_nano_board.kicad_pcb`

Design objective

Design a compact ATmega328P development board with USB programming, regulated power, reset and boot support, and the standard Nano-style header interface.

Board constraints

- Use a two-layer board with an approximately 43.2 mm by 17.8 mm outline and Nano-compatible header spacing.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Provide USB-C power and USB 2.0 data to the USB-to-UART bridge, including CC resistors and input protection.
- Support ATmega328P programming, reset, serial communication, SPI, I2C, analog inputs, digital GPIO, and the standard Nano power pins.
- Generate the 5 V rail, distribute 3.3 V from the USB bridge where needed, and include decoupling for every active device.
- Include the 16 MHz clock source, reset button, programming header, status LEDs, and two complete Nano-style breakout headers.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- ATMEGA328P-MU microcontroller
- FT232RL USB-to-UART bridge
- NCP1117-5.0 regulator
- 16 MHz ceramic resonator
- USB-C receptacle

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
