#!/usr/bin/env python3
"""hiper - CLI and console for the Hiper IoT A61 RGB lamp.

Local Tuya 3.3 protocol over TCP 6668. No cloud, no account, no internet.

    hiper on | off | toggle
    hiper status [--json]
    hiper mode set color|white|scene|music
    hiper set bright 1-100
    hiper set temp <kelvin>
    hiper set color <R> <G> <B>  or  hiper set color "#ff0019"
    hiper gradient "(255,0,0)" "(0,0,255)" [--duration 2] [--loop 0]
    hiper init --from devices.json
    hiper rescan
    hiper            # interactive console
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

try:
    import tinytuya
except ImportError:  # pragma: no cover
    sys.exit("tinytuya is missing: pip install tinytuya")

from i18n import AVAILABLE, DEFAULT, Lang

APP = "hiper"
VERSION = "1.1.0"

# --- datapoints (category "dj") --------------------------------------------
DP_SWITCH = "20"
DP_MODE = "21"
DP_BRIGHT = "22"
DP_TEMP = "23"
DP_COLOUR = "24"
DP_COUNTDOWN = "26"

BRIGHT_MIN, BRIGHT_MAX = 10, 1000
TEMP_MIN, TEMP_MAX = 0, 1000
KELVIN_WARM, KELVIN_COOL = 2700.0, 6500.0
MODES = ("white", "colour", "scene", "music")
DP_SEND_DELAY = 0.25
LAMP_NAME = "Hiper IoT A61 RGB"


class CliError(Exception):
    """User-facing error, printed without a traceback."""


# ===========================================================================
# configuration
# ===========================================================================

def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else Path(__file__).resolve().parent


def user_config_path() -> Path:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / APP / "hiper.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP / "hiper.json"


def config_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("HIPER_CONFIG")
    if env:
        paths.append(Path(env).expanduser())
    paths.append(user_config_path())
    paths.append(Path.home() / f".{APP}" / "hiper.json")
    paths.append(app_dir() / "hiper.json")
    paths.append(Path.cwd() / "hiper.json")
    return paths


def apply_env(cfg: dict) -> dict:
    for key, env_name in (
        ("id", "HIPER_ID"),
        ("key", "HIPER_KEY"),
        ("ip", "HIPER_IP"),
        ("version", "HIPER_VERSION"),
        ("lang", "HIPER_LANG"),
    ):
        value = os.environ.get(env_name)
        if value:
            cfg[key] = value
    return cfg


def load_config(explicit: str | None, t: Lang) -> tuple[dict, Path | None]:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise CliError(t("err.config_not_found", path=path))
        try:
            return apply_env(json.loads(path.read_text(encoding="utf-8-sig"))), path
        except (OSError, json.JSONDecodeError) as exc:
            raise CliError(t("err.config_unreadable", path=path, error=exc)) from exc

    for path in config_paths():
        if not path.exists():
            continue
        try:
            cfg = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CliError(t("err.config_unreadable", path=path, error=exc)) from exc
        if cfg.get("id") and cfg.get("key"):
            return apply_env(cfg), path

    raise CliError(f"{t('err.config_missing')}\n{t('err.config_hint')}")


def save_config(cfg: dict, current: Path | None, t: Lang) -> Path:
    targets: list[Path] = []
    if current is not None:
        targets.append(current)
    targets.append(user_config_path())
    targets.append(app_dir() / "hiper.json")

    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(cfg, indent=4, ensure_ascii=False), encoding="utf-8")
            return target
        except OSError:
            continue
    raise CliError(t("err.save_config"))


# ===========================================================================
# conversions
# ===========================================================================

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def pct_to_bright(pct: float) -> int:
    return int(round(BRIGHT_MIN + (BRIGHT_MAX - BRIGHT_MIN) * clamp(pct, 0, 100) / 100))


def bright_to_pct(value: int) -> int:
    return int(round((value - BRIGHT_MIN) / (BRIGHT_MAX - BRIGHT_MIN) * 100))


def kelvin_to_temp(kelvin: float, kmin: float, kmax: float) -> int:
    ratio = (clamp(kelvin, kmin, kmax) - kmin) / (kmax - kmin)
    return int(round(ratio * TEMP_MAX))


def temp_to_kelvin(value: int) -> int:
    kelvin = 2700 + (6500 - 2700) * clamp(value, 0, TEMP_MAX) / TEMP_MAX
    return int(round(kelvin / 10) * 10)


def rgb_to_colour(r: int, g: int, b: int) -> tuple[str, int, int, int]:
    """RGB 0-255 -> ('hHHHssssvvvv', h, s, v)."""
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    delta = mx - mn

    if delta == 0:
        hue = 0.0
    elif mx == rf:
        hue = (60 * ((gf - bf) / delta)) % 360
    elif mx == gf:
        hue = 60 * ((bf - rf) / delta) + 120
    else:
        hue = 60 * ((rf - gf) / delta) + 240

    sat = 0.0 if mx == 0 else delta / mx
    h, s, v = int(round(hue)) % 360, int(round(sat * 1000)), int(round(mx * 1000))
    return f"{h:04x}{s:04x}{v:04x}", h, s, v


def decode_colour(raw: str) -> tuple[int, int, int] | None:
    raw = str(raw)
    if len(raw) != 12:
        return None
    try:
        return tuple(int(raw[i:i + 4], 16) for i in (0, 4, 8))  # type: ignore[return-value]
    except ValueError:
        return None


def _parse_rgb_chunk(chunk: str, t: Lang) -> tuple[int, int, int]:
    chunk = chunk.strip().strip("()[]").strip()
    if chunk.startswith("#"):
        text = chunk.lstrip("#")
        if len(text) != 6:
            raise CliError(t("err.hex", value=chunk))
        try:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError as exc:
            raise CliError(t("err.hex", value=chunk)) from exc

    parts = [p for p in re.split(r"[,\s]+", chunk) if p]
    if len(parts) != 3:
        raise CliError(t("err.colour_three"))
    try:
        rgb = tuple(int(p) for p in parts)
    except ValueError as exc:
        raise CliError(t("err.colour_ints")) from exc
    if any(c < 0 or c > 255 for c in rgb):
        raise CliError(t("err.colour_range"))
    return rgb  # type: ignore[return-value]


def parse_color_args(values: list[str], t: Lang) -> tuple[int, int, int]:
    if len(values) == 1:
        return _parse_rgb_chunk(values[0], t)
    if len(values) == 3:
        return _parse_rgb_chunk(" ".join(values), t)
    raise CliError(t("err.colour_syntax"))


def parse_color_pair(argv: list[str], t: Lang) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    text = " ".join(argv)

    groups = re.findall(r"[\(\[]([^\)\]]*)[\)\]]", text)
    if len(groups) == 2:
        return _parse_rgb_chunk(groups[0], t), _parse_rgb_chunk(groups[1], t)
    if groups:
        raise CliError(t("err.two_colours"))

    hexes = re.findall(r"#[0-9a-fA-F]{6}", text)
    if len(hexes) == 2:
        return _parse_rgb_chunk(hexes[0], t), _parse_rgb_chunk(hexes[1], t)

    parts = [p for p in re.split(r"[,\s]+", text) if p]
    if len(parts) >= 6:
        return _parse_rgb_chunk(" ".join(parts[0:3]), t), _parse_rgb_chunk(" ".join(parts[3:6]), t)

    raise CliError(t("err.two_colours"))


# ===========================================================================
# transport
# ===========================================================================

def connect(cfg: dict, timeout: float = 5.0) -> tinytuya.Device:
    if not cfg.get("ip"):
        raise CliError("no IP")
    dev = tinytuya.Device(
        cfg["id"], cfg["ip"], cfg["key"], version=float(cfg.get("version", "3.3"))
    )
    dev.set_socketTimeout(timeout)
    dev.set_socketPersistent(False)
    return dev


def wrap_transport_error(exc: Exception, cfg: dict, t: Lang) -> CliError:
    name = type(exc).__name__
    message = str(exc)
    if "timeout" in name.lower() or "timed out" in message.lower():
        return CliError(t("err.timeout", ip=cfg.get("ip", "?")))
    return CliError(t("err.transport", type=name, error=message))


def write_dps(dev, dps: dict[str, object], cfg: dict, t: Lang) -> None:
    """Send datapoints one per packet.

    This firmware silently drops a DP that arrives bundled with another one,
    so every DP goes out in its own frame with a small pause.
    """
    items = list(dps.items())
    for index, (dp, value) in enumerate(items):
        try:
            result = dev.set_value(dp, value)
        except Exception as exc:  # noqa: BLE001
            raise wrap_transport_error(exc, cfg, t) from exc
        if isinstance(result, dict) and result.get("Error"):
            raise CliError(t("err.dp_rejected", dp=dp, error=result.get("Error")))
        if index < len(items) - 1:
            time.sleep(DP_SEND_DELAY)


def read_dps(dev, cfg: dict, t: Lang) -> dict:
    try:
        result = dev.status()
    except Exception as exc:  # noqa: BLE001
        raise wrap_transport_error(exc, cfg, t) from exc
    if not isinstance(result, dict) or result.get("Error"):
        raise CliError(t("err.status_read", result=result))
    return result.get("dps", {})


# ===========================================================================
# brightness: two different channels
# ===========================================================================

def effective_brightness(dps: dict) -> tuple[int, str]:
    """Actual brightness 0-1000 and its source: 'colour' (v) or 'white' (DP22).

    DP22 is the white-channel brightness. In colour mode brightness lives in the
    v field of colour_data, and DP22 keeps a stale value.
    """
    if dps.get(DP_MODE) == "colour":
        colour = decode_colour(dps.get(DP_COLOUR, ""))
        if colour:
            return colour[2], "colour"
    return int(dps.get(DP_BRIGHT, 0)), "white"


def apply_brightness(dev, cfg: dict, percent: float, t: Lang) -> str:
    if not 0 <= percent <= 100:
        raise CliError(t("err.bright_range"))

    raw = pct_to_bright(percent)
    dps = read_dps(dev, cfg, t)

    if dps.get(DP_MODE) == "colour":
        hue, sat, _ = decode_colour(dps.get(DP_COLOUR, "")) or (0, 1000, 0)
        payload = f"{hue:04x}{sat:04x}{raw:04x}"
        write_dps(dev, {DP_COLOUR: payload}, cfg, t)
        return t("cli.bright_colour", pct=round(percent), raw=raw)

    write_dps(dev, {DP_BRIGHT: raw}, cfg, t)
    return t("cli.bright", pct=round(percent), raw=raw)


# ===========================================================================
# gradient
# ===========================================================================

def run_gradient(
    dev, cfg: dict, start: tuple[int, int, int], end: tuple[int, int, int], t: Lang,
    steps: int = 24, duration: float = 2.0, loops: int = 1, pingpong: bool = False,
) -> str:
    steps = max(2, steps)
    duration = max(0.2, duration)
    delay = max(0.04, duration / (steps - 1))

    write_dps(dev, {DP_MODE: "colour"}, cfg, t)

    sent = 0
    started = time.monotonic()
    try:
        cycle = 0
        while loops == 0 or cycle < loops:
            reverse = pingpong and cycle % 2 == 1
            for index in range(steps):
                ratio = index / (steps - 1)
                if reverse:
                    ratio = 1.0 - ratio
                rgb = tuple(int(round(a + (b - a) * ratio)) for a, b in zip(start, end))
                payload = rgb_to_colour(*rgb)[0]
                try:
                    dev.set_value(DP_COLOUR, payload)
                except Exception as exc:  # noqa: BLE001
                    raise wrap_transport_error(exc, cfg, t) from exc
                sent += 1
                time.sleep(delay)
            cycle += 1
    except KeyboardInterrupt:
        return t("cli.gradient_stopped", frames=sent)

    return t(
        "cli.gradient",
        start=f"{start[0]:02x}{start[1]:02x}{start[2]:02x}",
        end=f"{end[0]:02x}{end[1]:02x}{end[2]:02x}",
        frames=sent,
        seconds=f"{time.monotonic() - started:.1f}",
    )


# ===========================================================================
# commands (one-shot CLI)
# ===========================================================================

def cmd_on(dev, cfg, args, t) -> None:
    write_dps(dev, {DP_SWITCH: True}, cfg, t)
    print(t("cli.on"))


def cmd_off(dev, cfg, args, t) -> None:
    write_dps(dev, {DP_SWITCH: False}, cfg, t)
    print(t("cli.off"))


def cmd_toggle(dev, cfg, args, t) -> None:
    current = bool(read_dps(dev, cfg, t).get(DP_SWITCH))
    write_dps(dev, {DP_SWITCH: not current}, cfg, t)
    print(t("cli.toggled_off") if current else t("cli.toggled_on"))


def cmd_status(dev, cfg, args, t) -> None:
    dps = read_dps(dev, cfg, t)
    if args.json:
        print(json.dumps(dps, ensure_ascii=False))
        return

    bright, source = effective_brightness(dps)
    line = t(
        "cli.status",
        state=t("cli.state_on") if dps.get(DP_SWITCH) else t("cli.state_off"),
        mode=dps.get(DP_MODE),
        pct=bright_to_pct(bright),
        raw=bright,
        source=t("cli.source_colour") if source == "colour" else t("cli.source_white"),
        kelvin=temp_to_kelvin(int(dps.get(DP_TEMP, 0))),
    )
    colour = decode_colour(dps.get(DP_COLOUR, ""))
    if colour:
        line += " " + t("cli.status_colour", h=colour[0], s=colour[1], v=colour[2])
    print(line)


def cmd_mode(dev, cfg, args, t) -> None:
    write_dps(dev, {DP_MODE: args.value}, cfg, t)
    print(t("cli.mode", mode=args.value))


def cmd_bright(dev, cfg, args, t) -> None:
    print(apply_brightness(dev, cfg, args.percent, t))


def cmd_temp(dev, cfg, args, t) -> None:
    kmin = float(cfg.get("kelvin_min", KELVIN_WARM))
    kmax = float(cfg.get("kelvin_max", KELVIN_COOL))
    kelvin = args.kelvin
    if kelvin < kmin or kelvin > kmax:
        kelvin = clamp(kelvin, kmin, kmax)
        write_dps(dev, {DP_MODE: "white", DP_TEMP: kelvin_to_temp(kelvin, kmin, kmax)}, cfg, t)
        print(t("cli.temp_clamped", kelvin=int(kelvin), low=int(kmin), high=int(kmax)))
        return
    write_dps(dev, {DP_MODE: "white", DP_TEMP: kelvin_to_temp(kelvin, kmin, kmax)}, cfg, t)
    print(t("cli.temp", kelvin=int(kelvin)))


def cmd_color(dev, cfg, args, t) -> None:
    r, g, b = parse_color_args(args.rgb, t)
    if max(r, g, b) == 0:
        raise CliError(t("err.black"))
    payload, hue, sat, val = rgb_to_colour(r, g, b)
    write_dps(dev, {DP_MODE: "colour", DP_COLOUR: payload}, cfg, t)
    print(t("cli.colour", hex=f"{r:02x}{g:02x}{b:02x}", h=hue, s=sat, v=val))


def cmd_gradient(dev, cfg, args, t) -> None:
    start, end = parse_color_pair(args.colors, t)
    print(run_gradient(
        dev, cfg, start, end, t,
        steps=args.steps, duration=args.duration, loops=args.loop, pingpong=args.pingpong,
    ))


def cmd_raw(dev, cfg, args, t) -> None:
    try:
        value = json.loads(args.value)
    except json.JSONDecodeError:
        value = args.value
    write_dps(dev, {args.dp: value}, cfg, t)
    print(t("cli.raw", dp=args.dp, value=value))


def cmd_rescan(dev, cfg, args, t) -> None:
    import contextlib
    import io

    from tinytuya import scanner

    snapshot = Path(tempfile.gettempdir()) / "hiper-scan.json"
    if snapshot.exists():
        snapshot.unlink()
    scanner.SNAPSHOTFILE = str(snapshot)

    print(t("cli.rescan_scanning", seconds=args.seconds), file=sys.stderr)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            scanner.scan(scantime=args.seconds)
    except Exception as exc:  # noqa: BLE001
        raise CliError(t("err.scan_failed", type=type(exc).__name__, error=exc)) from exc

    if not snapshot.exists():
        raise CliError(t("err.scan_empty"))

    data = json.loads(snapshot.read_text(encoding="utf-8-sig"))
    for item in data.get("devices", []):
        if item.get("id") == cfg["id"]:
            cfg["ip"] = item["ip"]
            cfg["version"] = item.get("ver", cfg.get("version", "3.3"))
            path = save_config(cfg, args._config_path, t)
            print(t("cli.rescan_found", ip=cfg["ip"], version=cfg["version"], path=path))
            return

    seen = ", ".join(f"{d.get('id')}@{d.get('ip')}" for d in data.get("devices", []))
    raise CliError(t("cli.rescan_failed", id=cfg["id"], seen=seen or "-"))


def cmd_info(dev, cfg, args, t) -> None:
    path = args._config_path
    shown = str(path) if path else "-"
    print(f"{APP} {VERSION}  [{t.code}]")
    print(f"device     : {cfg.get('name', '-')}")
    print(f"id         : {cfg['id']}")
    print(f"ip         : {cfg.get('ip', '-')}")
    print(f"protocol   : {cfg.get('version', '3.3')}")
    print(f"key        : {cfg['key'][:4]}...{cfg['key'][-4:]}")
    print(f"lang       : {cfg.get('lang', DEFAULT)}")
    print(f"config     : {shown}")


def cmd_init(dev, cfg, args, t) -> None:
    source: dict = {}
    if args.source:
        path = Path(args.source).expanduser()
        if not path.exists():
            raise CliError(t("err.init_source_missing", path=path))
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = data if isinstance(data, list) else [data]
        candidates = [d for d in items if d.get("key")]
        if not candidates:
            raise CliError(t("err.init_source", path=path))
        source = candidates[0]

    cfg = {
        "name": args.name or source.get("name") or LAMP_NAME,
        "id": args.id or source.get("id"),
        "key": args.key or source.get("key"),
        "ip": args.ip or source.get("ip"),
        "version": args.version or source.get("version") or "3.3",
        "lang": args.lang or DEFAULT,
        "kelvin_min": 2700,
        "kelvin_max": 6500,
    }
    if not (cfg["id"] and cfg["key"]):
        raise CliError(t("err.init_need"))

    path = save_config(cfg, None, t)
    print(t("cli.info_saved", path=path))

    if cfg.get("ip"):
        try:
            dps = read_dps(connect(cfg, 5.0), cfg, t)
            print(t("cli.info_tested", result=f"OK, {len(dps)} DP"))
        except CliError as exc:
            print(t("cli.info_tested", result=str(exc)))


# ===========================================================================
# interactive console bridge
# ===========================================================================

class ShellContext:
    def __init__(self, cfg: dict, t: Lang, timeout: float = 5.0, config_path: Path | None = None):
        self.cfg = cfg
        self.t = t
        self.timeout = timeout
        self.config_path = config_path
        self._dev = None
        self._dps: dict | None = None

    # transport ---------------------------------------------------------
    def device(self):
        if self._dev is None:
            self._dev = connect(self.cfg, self.timeout)
        return self._dev

    def status(self, refresh: bool = False) -> dict:
        if refresh or self._dps is None:
            self._dps = read_dps(self.device(), self.cfg, self.t)
        return self._dps

    def _write(self, dps: dict) -> None:
        write_dps(self.device(), dps, self.cfg, self.t)
        self._dps = None

    # description -------------------------------------------------------
    def describe(self, dps: dict | None = None) -> str:
        dps = self.status() if dps is None else dps
        if not dps:
            return self.t("shell.offline")
        state = self.t("cli.state_on") if dps.get(DP_SWITCH) else self.t("cli.state_off")
        bright, _ = effective_brightness(dps)
        kelvin = temp_to_kelvin(int(dps.get(DP_TEMP, 0)))
        if dps.get(DP_MODE) == "colour":
            colour = decode_colour(dps.get(DP_COLOUR, ""))
            if colour:
                return f"{state}, {bright_to_pct(bright)}%, {kelvin}K, h{colour[0]}"
        return f"{state}, {bright_to_pct(bright)}%, {kelvin}K"

    def describe_lines(self, dps: dict) -> list[str]:
        t = self.t
        state = t("shell.state_on") if dps.get(DP_SWITCH) else t("shell.state_off")
        bright, source = effective_brightness(dps)
        lines = [
            f"{t('shell.label_state'):<12}: {state}",
            f"{t('shell.label_mode'):<12}: {dps.get(DP_MODE)}",
            f"{t('shell.label_bright'):<12}: {bright_to_pct(bright)}% ({bright}/1000, {source})",
            f"{t('shell.label_temp'):<12}: {temp_to_kelvin(int(dps.get(DP_TEMP, 0)))}K",
        ]
        colour = decode_colour(dps.get(DP_COLOUR, ""))
        if colour:
            lines.append(f"{t('shell.label_colour'):<12}: h={colour[0]} s={colour[1]} v={colour[2]}")
        if dps.get(DP_COUNTDOWN):
            lines.append(f"{t('shell.label_timer'):<12}: {dps[DP_COUNTDOWN]}s")
        lines.append(f"{'dp':<12}: {json.dumps(dps, ensure_ascii=False)}")
        return lines

    def info_lines(self) -> list[str]:
        shown = str(self.config_path) if self.config_path else "-"
        return [
            f"device     : {self.cfg.get('name', '-')}",
            f"id         : {self.cfg['id']}",
            f"ip         : {self.cfg.get('ip', '-')}",
            f"protocol   : {self.cfg.get('version', '3.3')}",
            f"key        : {self.cfg['key'][:4]}...{self.cfg['key'][-4:]}",
            f"lang       : {self.t.code}",
            f"config     : {shown}",
        ]

    # commands ----------------------------------------------------------
    def on(self) -> None:
        self._write({DP_SWITCH: True})

    def off(self) -> None:
        self._write({DP_SWITCH: False})

    def toggle(self) -> str:
        current = bool(self.status(refresh=True).get(DP_SWITCH))
        self._write({DP_SWITCH: not current})
        return self.t("cli.toggled_off") if current else self.t("cli.toggled_on")

    def set_bright(self, percent: float) -> str:
        message = apply_brightness(self.device(), self.cfg, percent, self.t)
        self._dps = None
        return message

    def set_temp(self, kelvin: float) -> str:
        kmin = float(self.cfg.get("kelvin_min", KELVIN_WARM))
        kmax = float(self.cfg.get("kelvin_max", KELVIN_COOL))
        clamped = clamp(kelvin, kmin, kmax)
        self._write({DP_MODE: "white", DP_TEMP: kelvin_to_temp(clamped, kmin, kmax)})
        if clamped != kelvin:
            return self.t("cli.temp_clamped", kelvin=int(clamped), low=int(kmin), high=int(kmax))
        return self.t("cli.temp", kelvin=int(clamped))

    def set_color(self, argv: list[str]) -> str:
        r, g, b = parse_color_args(argv, self.t)
        if max(r, g, b) == 0:
            raise CliError(self.t("err.black"))
        payload, hue, sat, val = rgb_to_colour(r, g, b)
        self._write({DP_MODE: "colour", DP_COLOUR: payload})
        return self.t("cli.colour", hex=f"{r:02x}{g:02x}{b:02x}", h=hue, s=sat, v=val)

    def set_mode(self, mode: str) -> str:
        if mode not in MODES:
            raise CliError(self.t("err.mode_list", modes=", ".join(MODES)))
        self._write({DP_MODE: mode})
        return self.t("cli.mode", mode=mode)

    def raw(self, dp: str, value: str) -> str:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        self._write({dp: parsed})
        return self.t("cli.raw", dp=dp, value=parsed)

    def gradient(self, argv: list[str]) -> str:
        start, end = parse_color_pair(argv, self.t)
        duration = 2.0
        for index, token in enumerate(argv):
            if index >= 2 and re.fullmatch(r"\d+(?:\.\d+)?", token):
                duration = float(token)
        return run_gradient(self.device(), self.cfg, start, end, self.t, duration=duration)

    def set_lang(self, code: str) -> str:
        if not self.t.switch(code):
            raise CliError(self.t("shell.lang_usage"))
        self.cfg["lang"] = code
        try:
            save_config(self.cfg, self.config_path, self.t)
        except CliError:
            pass
        return self.t("shell.lang_set", lang=code)


# ===========================================================================
# CLI surface
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP,
        description="Local control for the Hiper IoT A61 RGB lamp.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-c", "--config", help="path to the device JSON config")
    parser.add_argument("--lang", choices=AVAILABLE, help="interface language (default: en)")
    parser.add_argument("--timeout", type=float, default=5.0, help="socket timeout, seconds")
    parser.add_argument("--version", action="version", version=f"{APP} {VERSION}")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("shell", help="interactive console").set_defaults(func=None)
    sub.add_parser("on", help="turn on").set_defaults(func=cmd_on)
    sub.add_parser("off", help="turn off").set_defaults(func=cmd_off)
    sub.add_parser("toggle", help="toggle").set_defaults(func=cmd_toggle)

    p = sub.add_parser("status", help="lamp state")
    p.add_argument("--json", action="store_true", help="raw datapoints as JSON")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("mode", help="work mode")
    mode_sub = p.add_subparsers(dest="mode_command", required=True)
    p_set = mode_sub.add_parser("set", help="set the mode")
    p_set.add_argument("value", choices=MODES)
    p_set.set_defaults(func=cmd_mode)

    p = sub.add_parser("set", help="set a parameter")
    set_sub = p.add_subparsers(dest="set_command", required=True)

    p_bright = set_sub.add_parser("bright", help="brightness 0-100 %")
    p_bright.add_argument("percent", type=float)
    p_bright.set_defaults(func=cmd_bright)

    p_temp = set_sub.add_parser("temp", help="colour temperature, kelvin")
    p_temp.add_argument("kelvin", type=float)
    p_temp.set_defaults(func=cmd_temp)

    p_color = set_sub.add_parser("color", help="colour: R G B (0-255) or #rrggbb")
    p_color.add_argument("rgb", nargs="+", metavar="R G B")
    p_color.set_defaults(func=cmd_color)

    p_grad = sub.add_parser("gradient", help="smooth transition between two colours")
    p_grad.add_argument("colors", nargs="+",
                        help="two colours: '(255,0,0) (0,0,255)' or '#ff0000 #0000ff'")
    p_grad.add_argument("--steps", type=int, default=24, help="frames (default: 24)")
    p_grad.add_argument("--duration", type=float, default=2.0, help="seconds (default: 2)")
    p_grad.add_argument("--loop", type=int, default=1, help="repetitions, 0 = forever")
    p_grad.add_argument("--pingpong", action="store_true", help="back and forth")
    p_grad.set_defaults(func=cmd_gradient)

    p_raw = sub.add_parser("raw", help="write a raw datapoint")
    p_raw.add_argument("dp")
    p_raw.add_argument("value")
    p_raw.set_defaults(func=cmd_raw)

    p_init = sub.add_parser("init", help="create the device config")
    p_init.add_argument("--from", dest="source", help="import from a tinytuya devices.json")
    p_init.add_argument("--id")
    p_init.add_argument("--key")
    p_init.add_argument("--ip")
    p_init.add_argument("--name")
    p_init.add_argument("--version", dest="version")
    p_init.set_defaults(func=cmd_init)

    p_scan = sub.add_parser("rescan", help="find the lamp again and update its IP")
    p_scan.add_argument("--seconds", type=int, default=18, help="scan duration (default: 18)")
    p_scan.set_defaults(func=cmd_rescan)

    sub.add_parser("info", help="show configuration").set_defaults(func=cmd_info)

    return parser


NO_DEVICE_COMMANDS = {cmd_info, cmd_rescan, cmd_init}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    t = Lang(args.lang or os.environ.get("HIPER_LANG") or DEFAULT)

    try:
        if args.command == "init":
            cmd_init(None, {}, args, t)
            return 0

        cfg, config_path = load_config(args.config, t)
        if args.lang:
            cfg["lang"] = args.lang
        t = Lang(cfg.get("lang", DEFAULT))
        args._config_path = config_path

        if not getattr(args, "command", None) or args.func is None:
            from shell_ui import Shell

            return Shell(ShellContext(cfg, t, args.timeout, config_path)).run()

        dev = None
        if args.func not in NO_DEVICE_COMMANDS:
            try:
                dev = connect(cfg, args.timeout)
            except CliError:
                raise CliError(t("err.no_ip"))

        args.func(dev, cfg, args, t)
        return 0
    except CliError as exc:
        print(f"{APP}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n{APP}: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
