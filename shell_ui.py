"""Интерактивная консоль hiper.

Эмуляция гостевой оболочки лампы: busybox-подобные команды, fastfetch с лого
Tuya, псевдо-/proc. Системный вывод намеренно английский (как на реальном
устройстве), переводится только собственный интерфейс.
"""
from __future__ import annotations

import os
import re
import shlex
import socket
import subprocess
import sys
from datetime import datetime, timedelta

from lineedit import Editor

APP = "hiper"
SHELL_VERSION = "hsh 1.1"
HOSTNAME = "tuya-a61"
KERNEL = "3.4.0-tuya-sdk"
OS_NAME = "TuyaOS 3.4.0 (armv7l)"

MEM_TOTAL_KB = 8 * 1024
DISK_TOTAL_MB = 12.0
BOOT_TIME = datetime.now() - timedelta(days=12, hours=4, minutes=31)

# --- цвета -----------------------------------------------------------------

_USE_COLOR = False


def enable_ansi() -> bool:
    global _USE_COLOR
    if os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty():
        _USE_COLOR = False
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:  # noqa: BLE001
            _USE_COLOR = False
            return False
    _USE_COLOR = True
    return True


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ORANGE = "\033[38;2;255;138;0m"
CYAN = "\033[38;2;110;200;230m"
GREEN = "\033[38;2;130;220;130m"
RED = "\033[38;2;255;110;110m"


def paint(text: str, *styles: str) -> str:
    if not _USE_COLOR or not styles:
        return text
    return "".join(styles) + text + RESET


# --- лого ------------------------------------------------------------------

_GLYPHS = {
    "T": ["█████", "  █  ", "  █  ", "  █  ", "  █  "],
    "U": ["█   █", "█   █", "█   █", "█   █", " ▀▀▀ "],
    "Y": ["█   █", "█   █", " ▀▀▀ ", "  █  ", "  █  "],
    "A": [" ▀▀▀ ", "█   █", "█▀▀▀█", "█   █", "█   █"],
}

LOGO = ["  ".join(_GLYPHS[ch][row] for ch in "TUYA") for row in range(5)]
LOGO_WIDTH = max(len(line) for line in LOGO)

# --- псевдосистема ---------------------------------------------------------

def uptime_human() -> str:
    total = datetime.now() - BOOT_TIME
    days = total.days
    hours, remainder = divmod(total.seconds, 3600)
    minutes = remainder // 60
    return f"{days} days, {hours}:{minutes:02d}" if days else f"{hours}:{minutes:02d}"


def mem_used_kb() -> int:
    drift = 12 * (0.5 + 0.5 * ((datetime.now().second % 20) / 20))
    return int(5100 + drift)


FS: dict[str, list[str]] = {
    "/": ["bin", "dev", "etc", "home", "proc", "sys", "tmp", "tuya", "usr", "var"],
    "/bin": ["busybox", "cat", "cp", "ls", "ps", "sh", "su"],
    "/etc": ["hostname", "passwd", "resolv.conf", "tuya.conf", "version"],
    "/proc": ["cpuinfo", "meminfo", "uptime", "version"],
    "/tmp": ["run.log"],
    "/tuya": ["app", "conf", "dps.json"],
    "/tuya/conf": ["wifi.conf", "mqtt.conf", "dp_map.json"],
    "/home": ["root"],
    "/home/root": [".profile", "log"],
    "/usr": ["lib", "share"],
    "/var": ["log"],
}

FILES: dict[str, str] = {
    "/etc/hostname": f"{HOSTNAME}\n",
    "/etc/version": "TuyaOS 3.4.0 (armv7l)\nbuild 2025-01-08\n",
    "/etc/tuya.conf": (
        "# Tuya local service\n"
        "tcp.port = 6668\n"
        "protocol = 3.3\n"
        "cloud.enabled = true\n"
        "local_key = ****************\n"
    ),
    "/etc/passwd": "root:x:0:0:root:/home/root:/bin/sh\ntuya:x:1000:1000:tuya:/tuya:/bin/sh\n",
    "/etc/resolv.conf": "nameserver 192.168.1.1\nnameserver 8.8.8.8\n",
    "/proc/cpuinfo": (
        "Processor\t: ARM968E-S rev 1 (v5l)\n"
        "BogoMIPS\t: 119.60\n"
        "Features\t: swp half thumb fastmult edsp\n"
        "CPU implementer\t: 0x41\n"
        "CPU architecture: 5TEJ\n"
        "CPU part\t: 0x926\n"
        "Hardware\t: BK7231N\n"
        "Serial\t\t: 000000000000\n"
    ),
    "/proc/version": f"Linux version {KERNEL} (tuya@build) #1 SMP PREEMPT armv7l\n",
    "/tmp/run.log": (
        "[    0.000000] Booting Linux on physical CPU 0x0\n"
        "[    2.418233] tuya_ipc: local service listening on 6668\n"
        "[    2.602911] wlan0: authenticated, ssid hidden\n"
    ),
    "/tuya/dps.json": '{"20":true,"21":"white","22":1000,"23":1000,"24":"000003e803e8"}\n',
    "/tuya/conf/wifi.conf": "ssid=home-2g\nmode=station\npower_save=0\n",
}

# (english, russian) — описания команд для help
DESC: dict[str, tuple[str, str]] = {
    "help": ("list commands", "список команд"),
    "exit": ("leave the console", "выйти из консоли"),
    "clear": ("clear the screen", "очистить экран"),
    "neofetch": ("logo and lamp summary", "логотип и сведения о лампе"),
    "status": ("lamp state", "состояние лампы"),
    "on": ("turn on", "включить"),
    "off": ("turn off", "выключить"),
    "toggle": ("toggle", "переключить"),
    "set": ("set bright|temp|color", "установить параметр"),
    "mode": ("work mode", "режим работы"),
    "gradient": ("smooth colour transition", "плавный переход цвета"),
    "raw": ("raw datapoint", "сырой DP"),
    "info": ("connection config", "конфигурация подключения"),
    "lang": ("switch language", "переключить язык"),
    "uname": ("kernel version", "версия ядра"),
    "hostname": ("device name", "имя устройства"),
    "whoami": ("current user", "текущий пользователь"),
    "id": ("user ids", "идентификаторы пользователя"),
    "pwd": ("current directory", "текущий каталог"),
    "cd": ("change directory", "сменить каталог"),
    "ls": ("list directory", "содержимое каталога"),
    "cat": ("print a file", "прочитать файл"),
    "echo": ("print text", "вывести текст"),
    "date": ("date and time", "дата и время"),
    "uptime": ("uptime and load", "время работы"),
    "free": ("memory usage", "память"),
    "df": ("disk usage", "диски"),
    "ps": ("process list", "процессы"),
    "dmesg": ("boot log", "журнал загрузки"),
    "ifconfig": ("network interfaces", "сетевые интерфейсы"),
    "ping": ("real ICMP ping", "реальный ICMP-пинг"),
    "curl": ("real HTTP request", "реальный HTTP-запрос"),
    "ssh": ("probe SSH port", "проверить SSH"),
    "telnet": ("probe telnet port", "проверить telnet"),
    "wifi": ("Wi-Fi parameters", "параметры Wi-Fi"),
    "history": ("command history", "история команд"),
    "sudo": ("run as root", "выполнить от root"),
    "reboot": ("self-test and restore state", "самопроверка и восстановление"),
    "poweroff": ("not permitted", "не разрешено"),
}

USAGE: dict[str, str] = {
    "help": "help [command]",
    "exit": "exit",
    "clear": "clear",
    "neofetch": "neofetch",
    "status": "status",
    "on": "on",
    "off": "off",
    "toggle": "toggle",
    "set": "set bright|temp|color ...",
    "mode": "mode set white|colour|color|scene|music",
    "gradient": "gradient (R,G,B) (R,G,B) [seconds]",
    "raw": "raw <dp> <value>",
    "info": "info",
    "lang": "lang en|ru",
    "uname": "uname [-a]",
    "hostname": "hostname",
    "whoami": "whoami",
    "id": "id",
    "pwd": "pwd",
    "cd": "cd [path]",
    "ls": "ls [-l] [path]",
    "cat": "cat <file>",
    "echo": "echo [text]",
    "date": "date",
    "uptime": "uptime",
    "free": "free [-h]",
    "df": "df [-h]",
    "ps": "ps",
    "dmesg": "dmesg",
    "ifconfig": "ifconfig",
    "ping": "ping [-c N] <host>",
    "curl": "curl [-I] [-s] <url>",
    "ssh": "ssh [user@]host [-p port]",
    "telnet": "telnet <host> [port]",
    "wifi": "wifi",
    "history": "history",
    "sudo": "sudo <command>",
    "reboot": "reboot [--off seconds]",
    "poweroff": "poweroff",
}


def _cwd_norm(path: str, cwd: str) -> str:
    if not path:
        return cwd
    base = cwd if not path.startswith("/") else "/"
    parts = [p for p in base.split("/") if p]
    for chunk in path.split("/"):
        if chunk in ("", "."):
            continue
        if chunk == "..":
            if parts:
                parts.pop()
            continue
        parts.append(chunk)
    return "/" + "/".join(parts)


class Shell:
    def __init__(self, ctx):
        self.ctx = ctx
        self.t = ctx.t
        self.cwd = "/home/root"
        self.history: list[str] = []
        self.running = True
        self.editor = Editor()
        self.editor.history = self.history
        self._build_commands()

    # -- утилиты --------------------------------------------------------

    @property
    def cfg(self) -> dict:
        return self.ctx.cfg

    def desc(self, name: str) -> str:
        pair = DESC.get(name, ("", ""))
        return pair[0] if self.t.code == "en" else pair[1]

    def state_line(self) -> str:
        try:
            return self.ctx.describe()
        except Exception:  # noqa: BLE001
            return paint(self.t("shell.offline"), RED)

    def error(self, message: str) -> None:
        print(paint(message, RED))

    def ok(self, message: str) -> None:
        print(paint(message, GREEN))

    # -- регистрация ----------------------------------------------------

    def _build_commands(self) -> None:
        c = self.commands = {}

        def add(name, handler, *aliases):
            c[name] = handler
            for alias in aliases:
                c[alias] = handler

        add("help", self.h_help)
        add("exit", self.h_exit, "quit", "logout")
        add("clear", self.h_clear, "cls")
        add("neofetch", self.h_neofetch, "fastfetch", "fetch", "logo", "ff")

        add("status", self.h_status, "state", "dps")
        add("on", self.h_on)
        add("off", self.h_off)
        add("toggle", self.h_toggle)
        add("set", self.h_set)
        add("mode", self.h_mode)
        add("gradient", self.h_gradient, "fade")
        add("raw", self.h_raw)
        add("info", self.h_info)
        add("lang", self.h_lang)

        add("uname", self.h_uname, "kernel")
        add("hostname", self.h_hostname)
        add("whoami", self.h_whoami)
        add("id", self.h_id)
        add("pwd", self.h_pwd)
        add("cd", self.h_cd)
        add("ls", self.h_ls, "dir")
        add("cat", self.h_cat, "less", "more")
        add("echo", self.h_echo)
        add("date", self.h_date)
        add("uptime", self.h_uptime)
        add("free", self.h_free)
        add("df", self.h_df)
        add("ps", self.h_ps, "top")
        add("dmesg", self.h_dmesg)
        add("ifconfig", self.h_ifconfig, "ip")
        add("ping", self.h_ping)
        add("curl", self.h_curl)
        add("ssh", self.h_ssh)
        add("telnet", self.h_telnet)
        add("wifi", self.h_wifi, "iwconfig")
        add("history", self.h_history)
        add("sudo", self.h_sudo)
        add("reboot", self.h_reboot)
        add("poweroff", self.h_poweroff, "shutdown", "halt")

    # -- автодополнение -------------------------------------------------

    def complete(self, line: str) -> list[str]:
        if line.endswith(" ") or not line:
            token, start = "", len(line)
        else:
            start = line.rfind(" ") + 1
            token = line[start:]
        words = line[:start].split()

        if not words:
            candidates = sorted({name for name in self.commands})
        elif words[0] == "set":
            candidates = ["bright", "temp", "color"] if len(words) == 1 else []
        elif words[0] == "mode":
            candidates = ["set"] if len(words) == 1 else ["white", "colour", "color", "scene", "music"]
        elif words[0] == "lang":
            candidates = ["en", "ru"]
        elif words[0] in ("cd", "cat", "ls"):
            candidates = self._path_complete(token) if "/" in token else sorted(FS)
        elif words[0] == "help":
            candidates = sorted(self.commands)
        else:
            candidates = []

        return [c for c in candidates if c.startswith(token)]

    @staticmethod
    def _path_complete(token: str) -> list[str]:
        base, _, fragment = token.rpartition("/")
        directory = base or "/"
        entries = FS.get(directory.rstrip("/") or "/", [])
        prefix = "" if directory == "/" else directory.rstrip("/")
        return [f"{prefix}/{name}" for name in entries if name.startswith(fragment)]

    # -- оболочка -------------------------------------------------------

    def banner(self) -> None:
        name = self.cfg.get("name") or "Hiper IoT A61 RGB"
        print()
        print(
            "  "
            + paint(f"{name} - ", BOLD, ORANGE)
            + self.state_line()
            + paint(self.t("shell.exit_hint"), DIM)
        )
        print(paint("  " + "─" * 62, DIM))
        print()

    def prompt(self) -> str:
        return (
            paint(f"root@{HOSTNAME}", ORANGE, BOLD)
            + paint(":", DIM)
            + paint(self.cwd, CYAN)
            + paint("$ ", BOLD)
        )

    def run(self) -> int:
        enable_ansi()
        self.banner()
        while self.running:
            try:
                line = self.editor.read(self.prompt(), self.complete)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue

            line = line.strip()
            if not line:
                continue
            try:
                self.dispatch(line)
            except SystemExit:
                break
            except Exception as exc:  # noqa: BLE001
                from hiper import CliError

                if isinstance(exc, CliError):
                    self.error(str(exc))
                else:
                    self.error(f"{type(exc).__name__}: {exc}")
        print(paint(self.t("shell.logout"), DIM))
        return 0

    def dispatch(self, line: str) -> None:
        try:
            argv = shlex.split(line, posix=True)
        except ValueError as exc:
            self.error(self.t("shell.parsing", error=exc))
            return
        if not argv:
            return
        if argv[0] == APP and len(argv) > 1:
            argv = argv[1:]

        handler = self.commands.get(argv[0])
        if handler is None:
            self.error(self.t("shell.not_found", cmd=argv[0]))
            print(paint("  " + self.t("shell.hint_help"), DIM))
            return
        handler(argv[1:])

    # -- help -----------------------------------------------------------

    def h_help(self, args: list[str]) -> None:
        if args:
            name = args[0]
            handler = self.commands.get(name)
            if handler is None:
                self.error(self.t("shell.not_found", cmd=name))
                return
            print(f"  {paint(USAGE.get(name, name), CYAN)} - {self.desc(name)}")
            return

        groups = [
            ("shell.help_lamp", ["status", "on", "off", "toggle", "set", "mode", "gradient", "raw", "info"]),
            ("shell.help_system", ["uname", "hostname", "whoami", "id", "date", "uptime", "free", "df", "ps", "dmesg", "reboot", "poweroff"]),
            ("shell.help_files", ["pwd", "cd", "ls", "cat", "echo"]),
            ("shell.help_network", ["ifconfig", "ping", "curl", "ssh", "telnet", "wifi"]),
            ("shell.help_misc", ["neofetch", "lang", "history", "clear", "help", "exit"]),
        ]

        print()
        print(paint("  " + self.t("shell.help_title"), BOLD, ORANGE))
        for title_key, names in groups:
            print()
            print(paint("  " + self.t(title_key), BOLD))
            for name in names:
                print(f"    {paint(USAGE.get(name, name).ljust(34), CYAN)}{self.desc(name)}")
        print()
        print(paint("  " + self.t("shell.help_footer1"), DIM))
        print(paint("  " + self.t("shell.help_footer2"), DIM))
        print()

    def h_exit(self, args: list[str]) -> None:
        self.running = False

    def h_clear(self, args: list[str]) -> None:
        print("\033[2J\033[H", end="")

    def h_lang(self, args: list[str]) -> None:
        if not args:
            print(paint(f"{self.t.code}", CYAN))
            return
        try:
            message = self.ctx.set_lang(args[0])
        except Exception:  # noqa: BLE001
            self.error(self.t("shell.lang_usage"))
            return
        self.ok(message)

    def h_neofetch(self, args: list[str]) -> None:
        t = self.t
        state = self.state_line()
        used = mem_used_kb()
        mem_pct = used * 100 // MEM_TOTAL_KB
        disk_pct = int(DISK_TOTAL_MB and (DISK_TOTAL_MB / DISK_TOTAL_MB) * 61)

        info = [
            paint(f"root@{HOSTNAME}", BOLD, ORANGE),
            paint("─" * 30, DIM),
            f"{paint('OS', ORANGE)}: {OS_NAME}",
            f"{paint('Host', ORANGE)}: {self.cfg.get('name') or 'Hiper IoT A61 RGB'}",
            f"{paint('Kernel', ORANGE)}: {KERNEL}",
            f"{paint('Uptime', ORANGE)}: {uptime_human()}",
            f"{paint('Packages', ORANGE)}: 24 (opkg)",
            f"{paint('Shell', ORANGE)}: {SHELL_VERSION}",
            f"{paint('CPU', ORANGE)}: BK7231N (ARM968E-S) @ 120 MHz",
            f"{paint('Memory', ORANGE)}: {used / 1024:.1f} MiB / {MEM_TOTAL_KB / 1024:.0f} MiB ({mem_pct}%)",
            f"{paint('Disk', ORANGE)}: 7.3 MiB / {DISK_TOTAL_MB:.0f} MiB ({disk_pct}%)",
            f"{paint('Local IP', ORANGE)}: {paint(self.cfg.get('ip', '-'), CYAN)}",
            f"{paint('Protocol', ORANGE)}: Tuya {self.cfg.get('version', '3.3')} · TCP 6668",
            f"{paint('Lang', ORANGE)}: {t.code}",
            f"{paint('State', ORANGE)}: {state}",
        ]

        print()
        for index in range(max(len(LOGO), len(info))):
            left = LOGO[index] if index < len(LOGO) else " " * LOGO_WIDTH
            right = info[index] if index < len(info) else ""
            print("  " + paint(left, ORANGE, BOLD) + "   " + right)
        print()

    # -- лампа ----------------------------------------------------------

    def h_status(self, args: list[str]) -> None:
        dps = self.ctx.status(refresh=True)
        print()
        for line in self.ctx.describe_lines(dps):
            print("  " + line)
        print()

    def h_on(self, args: list[str]) -> None:
        self.ctx.on()
        self.ok(self.t("cli.on"))

    def h_off(self, args: list[str]) -> None:
        self.ctx.off()
        self.ok(self.t("cli.off"))

    def h_toggle(self, args: list[str]) -> None:
        self.ok(self.ctx.toggle())

    def h_set(self, args: list[str]) -> None:
        if not args:
            self.error(self.t("shell.usage_set"))
            return
        what, rest = args[0], args[1:]
        try:
            if what == "bright":
                if not rest:
                    self.error(self.t("shell.usage_bright"))
                    return
                self.ok(self.ctx.set_bright(float(rest[0])))
            elif what == "temp":
                if not rest:
                    self.error(self.t("shell.usage_temp"))
                    return
                self.ok(self.ctx.set_temp(float(rest[0])))
            elif what == "color":
                if not rest:
                    self.error(self.t("shell.usage_color"))
                    return
                self.ok(self.ctx.set_color(rest))
            else:
                self.error(self.t("shell.unknown_set", what=what))
        except ValueError:
            self.error(self.t("shell.usage_set"))

    def h_mode(self, args: list[str]) -> None:
        if len(args) >= 2 and args[0] == "set":
            self.ok(self.ctx.set_mode(args[1]))
        elif args:
            self.ok(self.ctx.set_mode(args[0]))
        else:
            self.error(self.t("shell.usage_mode"))

    def h_gradient(self, args: list[str]) -> None:
        if len(args) < 2:
            self.error(self.t("shell.usage_gradient"))
            return
        self.ok(self.ctx.gradient(args))

    def h_raw(self, args: list[str]) -> None:
        if len(args) < 2:
            self.error(self.t("shell.usage_raw"))
            return
        self.ok(self.ctx.raw(args[0], args[1]))

    def h_info(self, args: list[str]) -> None:
        for line in self.ctx.info_lines():
            print("  " + line)

    # -- система (английский, как на устройстве) ------------------------

    def h_uname(self, args: list[str]) -> None:
        if "-a" in args:
            print(f"Linux {HOSTNAME} {KERNEL} #1 SMP PREEMPT Wed Jan 8 11:42:19 CST 2025 armv7l GNU/Linux")
        else:
            print("Linux")

    def h_hostname(self, args: list[str]) -> None:
        print(HOSTNAME)

    def h_whoami(self, args: list[str]) -> None:
        print("root")

    def h_id(self, args: list[str]) -> None:
        print("uid=0(root) gid=0(root) groups=0(root)")

    def h_pwd(self, args: list[str]) -> None:
        print(self.cwd)

    def h_cd(self, args: list[str]) -> None:
        target = _cwd_norm(args[0] if args else "/home/root", self.cwd)
        if target in FS:
            self.cwd = target
            return
        self.error(f"cd: {target}: No such file or directory")

    def h_ls(self, args: list[str]) -> None:
        long_format = any(a.startswith("-") and "l" in a for a in args)
        paths = [a for a in args if not a.startswith("-")]
        target = _cwd_norm(paths[0], self.cwd) if paths else self.cwd

        if target in FILES:
            print(target.rsplit("/", 1)[-1])
            return
        entries = FS.get(target)
        if entries is None:
            self.error(f"ls: {target}: No such file or directory")
            return
        if not long_format:
            print("  ".join(entries))
            return

        rows = []
        for name in entries:
            sub = _cwd_norm(name, target)
            if sub in FS:
                rows.append(("drwxr-xr-x", "4096", name))
            else:
                rows.append(("-rw-r--r--", str(120 + len(name) * 37), name))
        print(f"total {len(rows)}")
        for perms, size, name in rows:
            print(f"{perms} 1 root     root {size:>6} {name}")

    def h_cat(self, args: list[str]) -> None:
        if not args:
            self.error("usage: cat <file>")
            return
        target = _cwd_norm(args[0], self.cwd)
        content = FILES.get(target)
        if content is None:
            if target in FS:
                self.error(f"cat: {target}: Is a directory")
            else:
                self.error(f"cat: {target}: No such file or directory")
            return
        print(content, end="")

    def h_echo(self, args: list[str]) -> None:
        print(" ".join(args))

    def h_date(self, args: list[str]) -> None:
        print(datetime.now().strftime("%a %b %d %H:%M:%S %Z %Y"))

    def h_uptime(self, args: list[str]) -> None:
        print(f"{datetime.now().strftime('%H:%M:%S')} up {uptime_human()},  "
              f"load average: 0.14, 0.09, 0.05")

    def h_free(self, args: list[str]) -> None:
        used = mem_used_kb()
        print()
        print("              total        used        free      shared")
        print(f"Mem:      {MEM_TOTAL_KB:>9} KiB {used:>9} KiB {MEM_TOTAL_KB - used:>9} KiB {0:>9} KiB")
        print(f"Swap:     {0:>9} KiB {0:>9} KiB {0:>9} KiB")
        print()

    def h_df(self, args: list[str]) -> None:
        used = 7.3
        print()
        print("Filesystem      Size  Used Avail Use% Mounted on")
        print(f"/dev/mtdblock3  {DISK_TOTAL_MB:>4.1f}M {used:>4.1f}M {DISK_TOTAL_MB - used:>4.1f}M  "
              f"{int(used / DISK_TOTAL_MB * 100):>2}% /")
        print(f"tmpfs            {2.0:>4.1f}M {0.1:>4.1f}M {1.9:>4.1f}M  {5:>2}% /tmp")
        print()

    def h_ps(self, args: list[str]) -> None:
        rows = [(1, "/sbin/init"), (42, "tuya_ipc"), (57, "ty_wifi"), (63, "tuya_mqtt"), (88, "hsh")]
        print()
        print("  PID USER       VSZ STAT COMMAND")
        for pid, cmd in rows:
            print(f"{pid:>5} root      {1024 - pid:>4} S    {cmd}")
        print()

    def h_dmesg(self, args: list[str]) -> None:
        lines = [
            "Booting Linux on physical CPU 0x0",
            f"Linux version {KERNEL} (tuya@build) #1 SMP PREEMPT",
            "Memory: 8192KiB available",
            "mtd: flash 12 MiB detected",
            "wlan0: authenticated",
            "tuya_ipc: local service listening on 6668",
        ]
        for index, line in enumerate(lines):
            print(f"[{index * 0.4 + 0.2:12.6f}] {line}")

    def h_ifconfig(self, args: list[str]) -> None:
        print()
        print("wlan0     Link encap:Ethernet  HWaddr 00:00:00:00:00:00")
        print(f"          inet addr:{self.cfg.get('ip', '-')}  Bcast:192.168.1.255  Mask:255.255.255.0")
        print("          UP BROADCAST RUNNING MULTICAST  MTU:1500")
        print("          RX packets:128473 errors:0 dropped:12")
        print("          TX packets:40211 errors:0 dropped:0")
        print()
        print("lo        Link encap:Local Loopback")
        print("          inet addr:127.0.0.1  Mask:255.0.0.0")
        print()

    @staticmethod
    def _decode(data: bytes) -> str:
        for encoding in ("utf-8", "cp866", "cp1251"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", "replace")

    def h_ping(self, args: list[str]) -> None:
        host = None
        count = 4
        index = 0
        while index < len(args):
            token = args[index]
            if token in ("-c", "-n") and index + 1 < len(args):
                try:
                    count = max(1, int(args[index + 1]))
                except ValueError:
                    self.error(self.t("shell.usage_ping"))
                    return
                index += 2
                continue
            if not token.startswith("-"):
                host = token
            index += 1

        if not host:
            self.error(self.t("shell.usage_ping"))
            return

        if os.name == "nt":
            cmd = ["ping", "-n", str(count), "-w", "2000", host]
        else:
            cmd = ["ping", "-c", str(count), "-W", "2", host]

        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=count * 3 + 10)
        except FileNotFoundError:
            self.error("ping: system ping not available")
            return
        except subprocess.TimeoutExpired:
            self.error("ping: timed out")
            return

        print((self._decode(proc.stdout) + self._decode(proc.stderr)).rstrip())

    def h_curl(self, args: list[str]) -> None:
        import urllib.error
        import urllib.request

        head = False
        url = None
        limit = 4000
        for token in args:
            if token in ("-I", "--head"):
                head = True
            elif token.startswith("-"):
                continue
            else:
                url = token

        if not url:
            self.error(self.t("shell.usage_curl"))
            return
        if not re.match(r"^https?://", url):
            url = "http://" + url

        request = urllib.request.Request(
            url, method="HEAD" if head else "GET",
            headers={"User-Agent": "hiper/curl", "Accept": "*/*"},
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                print(f"HTTP {response.status} {response.reason}")
                for key, value in response.headers.items():
                    print(f"{key}: {value}")
                if head:
                    return
                body = response.read(limit + 1)
                print()
                text = body[:limit].decode("utf-8", "replace")
                print(text, end="" if text.endswith("\n") else "\n")
                if len(body) > limit:
                    print(paint(f"... (output truncated at {limit} B)", DIM))
        except urllib.error.HTTPError as exc:
            print(f"HTTP {exc.code} {exc.reason}")
        except urllib.error.URLError as exc:
            self.error(f"curl: ({exc.reason})")
        except Exception as exc:  # noqa: BLE001
            self.error(f"curl: {type(exc).__name__}: {exc}")

    def _probe_port(self, host: str, port: int, program: str) -> None:
        try:
            with socket.create_connection((host, port), timeout=4) as sock:
                print(f"{program}: connected to {host}:{port}")
                sock.settimeout(2)
                try:
                    banner = sock.recv(256)
                except (socket.timeout, OSError):
                    banner = b""
                if banner:
                    print(paint("banner: ", DIM) + self._decode(banner).strip())
                else:
                    print(paint("  port is open, no banner", DIM))
        except ConnectionRefusedError:
            self.error(f"{program}: connect to host {host} port {port}: Connection refused")
        except socket.timeout:
            self.error(f"{program}: connect to host {host} port {port}: Connection timed out")
        except OSError as exc:
            self.error(f"{program}: {host}:{port}: {exc}")

        if host == self.cfg.get("ip"):
            print(paint("  " + self.t("shell.ssh_note1"), DIM))
            print(paint("  " + self.t("shell.ssh_note2"), DIM))

    @staticmethod
    def _parse_host_port(args: list[str], default_port: int) -> tuple[str | None, int]:
        host = None
        port = default_port
        index = 0
        while index < len(args):
            token = args[index]
            if token in ("-p", "-P") and index + 1 < len(args):
                try:
                    port = int(args[index + 1])
                except ValueError:
                    return None, default_port
                index += 2
                continue
            if not token.startswith("-"):
                host = token
            index += 1
        if host and host.count(":") == 1:
            host, _, raw_port = host.partition(":")
            try:
                port = int(raw_port)
            except ValueError:
                pass
        if host and "@" in host:
            host = host.split("@", 1)[1]
        return host, port

    def h_ssh(self, args: list[str]) -> None:
        host, port = self._parse_host_port(args, 22)
        if not host:
            self.error(self.t("shell.usage_ssh"))
            return
        self._probe_port(host, port, "ssh")

    def h_telnet(self, args: list[str]) -> None:
        host, port = self._parse_host_port(args, 23)
        if not host:
            self.error(self.t("shell.usage_telnet"))
            return
        self._probe_port(host, port, "telnet")

    def h_wifi(self, args: list[str]) -> None:
        print("wlan0     IEEE 802.11  ESSID:\"home-2g\"")
        print("          Mode:Managed  Frequency:2.437 GHz")
        print("          Bit Rate=72.2 Mb/s   Signal level=-52 dBm")
        print("          Link Quality=61/70  Tx-Power=20 dBm")

    def h_history(self, args: list[str]) -> None:
        for index, line in enumerate(self.history, start=1):
            print(f"{index:>4}  {line}")

    def h_sudo(self, args: list[str]) -> None:
        if not args:
            self.error("usage: sudo <command>")
            return
        print(paint("you are already root", DIM))
        self.dispatch(" ".join(args))

    def h_reboot(self, args: list[str]) -> None:
        off = 2.0
        if "--off" in args:
            try:
                off = max(0.0, float(args[args.index("--off") + 1]))
            except (IndexError, ValueError):
                self.error("usage: reboot [--off seconds]")
                return
        self.ok(self.ctx.reboot(off))

    def h_poweroff(self, args: list[str]) -> None:
        self.error(self.t("shell.reboot_denied"))
        print(paint("  " + self.t("shell.reboot_note"), DIM))
