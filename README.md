# hiper

> **Authorship:** the code in this repository was written by an AI agent
> (OpenCode, DeepSeek V4.1 Flash) from the owner's specification and tested by
> the owner on a real lamp. See [How it was made](#how-it-was-made) and
> [AUTHORS.md](AUTHORS.md).

Local CLI and interactive console for the **Hiper IoT A61 RGB** lamp.
Everything runs over the Tuya 3.3 local protocol on TCP 6668 — no cloud, no
account, no vendor app, no internet. The lamp only has to be on the same
Wi-Fi network.

```
$ hiper status
on  mode=colour brightness=55% (554, colour) temp=6500K colour=h354 s1000 v1000

$ hiper set color 255 0 25
colour: #ff0019 -> h=354 s=1000 v=1000
```

Running `hiper` without arguments opens a small guest console that looks like
the shell of the lamp itself: busybox-style commands, `neofetch` with a Tuya
logo, and an emulated `/proc`. Lamp control inside that console is real; the
system commands are decoration.

---

## How it was made

This project was **written by an AI agent** (OpenCode, model DeepSeek V4.1
Flash) from a specification given by the repository owner. The requirements,
device, command set, console behaviour and packaging targets were defined by
the owner; the code, documentation and build scripts were produced by the
model. The owner tested every step against a physical lamp.

---

## Requirements

| Platform | What you need |
|---|---|
| Windows | Python 3.9+, `tinytuya`, `pyinstaller` (only to build the exe) |
| Linux / WSL | Python 3.9+, `tinytuya`, `pip` |
| Termux (Android) | Python, `tinytuya` |

The lamp must be reachable at a fixed IP on your LAN. A DHCP reservation on the
router is strongly recommended; if the address changes, `hiper rescan` finds
the lamp again.

---

## Getting the `local_key`

The lamp does not expose its local key over the network. You need a free Tuya
IoT Platform account **once**, only to read the key; after that nothing talks
to the cloud.

1. Create an account at <https://iot.tuya.com> and a Cloud project
   (region **Central Europe** for EU devices). Note the *Access ID* and
   *Access Secret*.
2. In *Devices → Link Tuya App Account*, scan the QR code with the
   **Smart Life** app. The OEM app (Hiper IoT) cannot be linked to the IoT
   platform, so the lamp has to be re-paired to Smart Life first.
3. In *API Explorer / Device Management* read the device `id` and `local_key`.
4. Create the config:

   ```bash
   hiper init --id <device-id> --key <local-key> --ip <lamp-ip>
   ```

   or import an existing `tinytuya` file:

   ```bash
   hiper init --from devices.json
   ```

`hiper init` writes the config and immediately tries to read the lamp, so you
know at once whether the key and IP are right. Re-pairing the lamp in the app
issues a **new** key — run `init` again after that.

---

## Configuration

The device config is **always external**. It is never compiled into the
binary; the executable only knows where to look for it.

Search order:

1. `--config <path>`
2. `HIPER_CONFIG` environment variable
3. `%LOCALAPPDATA%\hiper\hiper.json` (Windows) or
   `~/.config/hiper/hiper.json` (Linux, WSL, Termux)
4. `~/.hiper/hiper.json`
5. `hiper.json` next to the executable
6. `hiper.json` in the current directory

Environment overrides: `HIPER_ID`, `HIPER_KEY`, `HIPER_IP`,
`HIPER_VERSION`, `HIPER_LANG`.

```json
{
    "name": "Hiper IoT A61 RGB",
    "id": "<device-id>",
    "key": "<local_key>",
    "ip": "192.168.1.50",
    "version": "3.3",
    "lang": "en",
    "kelvin_min": 2700,
    "kelvin_max": 6500
}
```

---

## Commands

```bash
hiper on
hiper off
hiper toggle
hiper status [--json]

hiper mode set color|white|scene|music

hiper set bright 1-100          # percent
hiper set temp 1000-6000        # kelvin, clamped to the lamp range
hiper set color 255 0 25        # R G B, 0-255
hiper set color "#ff0019"       # or hex

hiper gradient "(255,0,0)" "(0,0,255)"           # 2 s transition
hiper gradient "(255,0,0)" "(0,0,255)" --loop 0  # forever, Ctrl+C to stop
hiper gradient "#ff0000" "#0000ff" --pingpong

hiper raw 22 800                # write a raw datapoint

hiper init --id <id> --key <key> --ip <ip>
hiper init --from devices.json
hiper rescan                    # find the lamp again after an IP change
hiper info                      # config summary, key is masked

hiper --lang ru                 # one-shot language override
hiper shell                     # console (same as no arguments)
```

Exit codes: `0` success, `1` error, `130` interrupted.

`hiper status --json` prints the raw datapoints, which is handy for scripts:

```powershell
$dps = hiper status --json | ConvertFrom-Json
if ($dps.'20') { "lamp is on" }
```

### Gradient

`gradient` takes two colours in any of these forms:

```bash
hiper gradient "(255,0,0)" "(0,0,255)"
hiper gradient "#ff0000" "#0000ff"
hiper gradient 255 0 0 0 0 255
```

Options: `--steps N` (frames, default 24), `--duration S` (default 2),
`--loop N` (`0` = forever), `--pingpong`.

---

## Interactive console

```
Hiper IoT A61 RGB - on, 55%, 6500K, h354, to exit type 'exit'. Help - hiper help
──────────────────────────────────────────────────────────────

root@tuya-a61:/home/root$
```

- **Tab** completes commands, then their arguments (`set ` → `bright temp
  color`, `mode set ` → modes, `lang ` → languages, paths for `cd`/`cat`/`ls`).
- **↑ / ↓** walks the history; `history` prints it.
- `help` lists everything, `help <command>` explains one command.
- `lang en|ru` switches the interface language (default **English**); the
  choice is saved in the config.

Lamp commands: `status`, `on`, `off`, `toggle`, `set bright|temp|color`,
`mode set`, `gradient`, `raw`, `info`.

Emulated system: `uname`, `hostname`, `whoami`, `id`, `pwd`, `cd`, `ls`, `cat`,
`echo`, `date`, `uptime`, `free`, `df`, `ps`, `dmesg`, `ifconfig`, `wifi`,
`dmesg`, `reboot` (refuses), `sudo` (you are already root).

`free`, `df`, `ps`, `neofetch` and `/proc` report a **fictional** device:
8 MiB RAM, 12 MiB flash, BK7231N. That is part of the joke, the real lamp is
not identical.

`neofetch` / `fastfetch` draws an orange Tuya logo next to the device summary.

Real network tools:

- `ping [-c N] <host>` calls the system `ping`.
- `curl [-I] <url>` performs a real HTTP request through Python's
  `urllib` (no external `curl` needed).
- `ssh` and `telnet` honestly probe the port and report that the lamp runs
  **no sshd/telnetd** — the only service is Tuya on TCP 6668.

System command output stays English, like on a real device shell; only the
tool's own interface is translated.

---

## Install

### Windows — single .exe

```powershell
cd hiper-cli
python -m pip install tinytuya pyinstaller
python build.py --install
```

`build.py`:

1. takes the key from `..\tuya-lamp\devices.json` (or your existing
   `device.json`),
2. builds one-file `dist\hiper.exe` (about 15 MB),
3. copies it to `%LOCALAPPDATA%\Programs\hiper` and adds that folder to the
   user `PATH`,
4. copies the device config to `%LOCALAPPDATA%\hiper\hiper.json`.

**Restart the terminal** afterwards, otherwise `hiper` is not found yet.
The config is not embedded in the exe: replace `hiper.json` and the same
binary serves another lamp.

### Linux / WSL without root

```bash
bash scripts/wsl-install.sh
```

Installs `tinytuya` with `pip --user`, copies the modules to
`~/.local/lib/hiper`, writes a launcher to `~/.local/bin/hiper`, puts the
config into `~/.config/hiper/hiper.json` and adds `~/.local/bin` to `PATH`.
No `sudo` needed.

A real ELF build is possible too, but PyInstaller needs the Python shared
library (`sudo apt install libpython3.x`); the script `scripts/wsl-build.sh`
is only useful once that package is present.

### Termux

```bash
bash scripts/termux-install.sh
```

PyInstaller does not work on Android/Termux, so the script installs hiper as
a Python package with a launcher in `$PREFIX/bin/hiper`.

### From source, anywhere

```bash
python -m pip install tinytuya
python hiper.py status
```

or install the package:

```bash
python -m pip install .
hiper status
```

---

## Firmware quirks

These are encoded in the code, but they matter if you modify it:

1. **One DP per packet.** If two datapoints arrive in one packet, the firmware
   silently drops one. hiper sends them one by one, 250 ms apart.
2. **`colour_data` is hex, not JSON**: `hHHHssssvvvv` — hue 0–360,
   saturation and value 0–1000. Tuya documents this DP as JSON; this lamp
   sends 12 hex characters.
3. **Brightness starts at 10**, so `set bright 0` gives 10 (≈1 %).
4. **Switching to `colour` mode resets brightness** to the firmware default
   (~587). Set the colour first, then the brightness.
5. **`DP22` is the white-channel brightness.** In colour mode the real
   brightness lives in the `v` field of `colour_data`, and `DP22` keeps a
   stale value. hiper reads and writes the right channel automatically.
6. `music_data` / `control_data` use s/v in 0–255, unlike `colour_data`
   (0–1000).

Datapoint map:

| DP | Meaning | Values |
|---|---|---|
| 20 | switch | `true` / `false` |
| 21 | mode | `white`, `colour`, `scene`, `music` |
| 22 | white brightness | 10–1000 |
| 23 | colour temperature | 0–1000 (2700–6500 K) |
| 24 | colour data | `hHHHssssvvvv` |
| 25 | scene | 12-byte hex |
| 26 | countdown | seconds |

---

## Security

`local_key` is effectively the lamp's password. It lives only in the external
config, is masked by `hiper info`, and must never be committed. The salt of
this project is the same as for the lamp: anyone on your LAN with the key can
control it.

`.gitignore` excludes `device.json`, `hiper.json`, `dist/`, `build/`, `*.spec`
and `__pycache__/`.

---

## License

MIT — see [LICENSE](LICENSE).

Russian documentation: [README.ru.md](README.ru.md).
