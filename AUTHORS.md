# Authors

## I114rk — owner, requirements, hardware

- Defined the goal: local-only control for the Hiper IoT A61 RGB lamp.
- Chose the device and provided physical access to it.
- Specified the command set, the interactive console, the banner text, the
  busybox/fastfetch emulation (8 MiB RAM, 12 MiB flash, invented device info),
  Tab completion, the language switcher and the target platforms
  (Windows `.exe` in `PATH`, WSL/Linux, Termux).
- Tested every step against the real lamp and reported firmware behaviour.

## OpenCode agent (DeepSeek V4.1 Flash) — code and documentation

- Wrote `hiper.py`, `shell_ui.py`, `i18n.py`, `lineedit.py`, `build.py`.
- Discovered the datapoint map and the firmware quirks (one DP per packet,
  `colour_data` as 12 hex characters, brightness reset on mode change,
  separate brightness channels for white and colour).
- Implemented the Windows Tab-completion editor (no `readline` on Windows),
  the gradient engine, the shell emulation and real `ping`/`curl`/port probes.
- Wrote the build/install scripts, README (EN/RU), this file and the tests
  run during development.

The human authored the requirements; the AI authored the implementation.
