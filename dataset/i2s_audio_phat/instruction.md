Build a complete KiCad project for `i2s_audio_phat` from this engineering brief.

Save the finished project in `/workspace/final_project` using:
- `/workspace/final_project/i2s_audio_phat.kicad_pro`
- `/workspace/final_project/i2s_audio_phat.kicad_sch`
- `/workspace/final_project/i2s_audio_phat.kicad_pcb`

Design objective

Design a Raspberry Pi Zero pHAT with stereo audio conversion, HAT identification memory, regulated analog power, and line, headphone, and microphone connections.

Board constraints

- Use a two-layer board with an approximately 30 mm by 65 mm Raspberry Pi Zero pHAT outline.
- Use a continuous closed board outline, practical component placement, mounting features where specified, and clearly labeled connectors and controls.

Electrical and interface requirements

- Connect the Pi header I2S, I2C, GPIO, power, and ground signals to the codec and identification circuitry.
- Implement the codec clocking, analog input path, line output, headphone output, microphone input, filtering, and bias networks.
- Provide the HAT EEPROM and its write-protection behavior on the identification bus.
- Separate analog and digital return currents, decouple every supply pin, and keep clock and analog traces away from noisy power paths.

Core components

Use these parts for the core functions. Select appropriate supporting passives, protection devices, connectors, and power components to complete the design.

- WM8731 audio codec
- TPS79333 low-noise regulator
- CAT24C32 EEPROM
- 12.288 MHz oscillator
- Raspberry Pi header and audio jacks

Completion requirements

- Create both a complete schematic and a fully placed and routed PCB.
- Assign valid KiCad footprints to every schematic component and keep schematic and PCB connectivity consistent.
- Route every specified external interface, power rail, ground connection, and required internal signal.
- Add decoupling, pull resistors, filtering, protection, test access, and copper pours appropriate to the circuit.
- Apply suitable trace widths, clearances, differential-pair geometry, and return paths for the expected current and signal speed.
- Run KiCad ERC and DRC, resolve actionable errors, and save the final project files.
