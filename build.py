"""Сборка hiper.exe (PyInstaller, onefile).

    python build.py            # собрать
    python build.py --install  # собрать и установить в PATH
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEVICE_JSON = HERE / "device.json"
TINYTUYA_DEVICES = HERE.parent / "tuya-lamp" / "devices.json"
DIST = HERE / "dist"
EXE_NAME = "hiper.exe" if os.name == "nt" else "hiper"
EXE = DIST / EXE_NAME


def prepare_device() -> None:
    if DEVICE_JSON.exists():
        print(f"[1/3] device.json уже есть")
        return

    if not TINYTUYA_DEVICES.exists():
        sys.exit(f"Нет {TINYTUYA_DEVICES}\nСначала получите local_key: python ..\\tuya-lamp\\fetch_keys.py")

    devices = json.loads(TINYTUYA_DEVICES.read_text(encoding="utf-8"))
    candidates = [d for d in devices if d.get("key") and d.get("ip")]
    if not candidates:
        sys.exit("В devices.json нет устройства с ключом и IP")

    dev = candidates[0]
    config = {
        "name": dev.get("name") or "hiper",
        "id": dev["id"],
        "key": dev["key"],
        "ip": dev["ip"],
        "version": dev.get("version", "3.3"),
        "kelvin_min": 2700,
        "kelvin_max": 6500,
    }
    DEVICE_JSON.write_text(json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"[1/3] создан {DEVICE_JSON.name} ({config['name']} @ {config['ip']})")


def build() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "hiper",
        "--collect-all", "tinytuya",
        "--distpath", str(DIST),
        "--workpath", str(HERE / "build"),
        "--specpath", str(HERE),
        "--noconfirm",
        "--clean",
        str(HERE / "hiper.py"),
    ]
    print("[2/3] сборка...")
    subprocess.run(cmd, check=True, cwd=HERE)

    if not EXE.exists():
        sys.exit("PyInstaller не создал exe")
    size = EXE.stat().st_size / 1024 / 1024
    print(f"[3/3] готово: {EXE} ({size:.1f} МБ)")


def copy_with_retry(source: Path, target: Path, attempts: int = 8) -> None:
    """Скопировать файл, пережидая блокировку антивирусом/запущенным процессом."""
    import time

    last: Exception | None = None
    for attempt in range(attempts):
        try:
            shutil.copy2(source, target)
            return
        except PermissionError as exc:
            last = exc
            print(f"  файл занят, повтор {attempt + 1}/{attempts}...")
            time.sleep(1.0)
    raise PermissionError(
        f"Не удалось записать {target}: файл занят.\n"
        f"Закройте запущенные экземпляры hiper и повторите."
    ) from last


def user_config() -> Path:
    """Where the installed binary looks for the device config."""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "hiper" / "hiper.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "hiper" / "hiper.json"


def install_config() -> None:
    """Copy device.json to the per-user config. Never bake it into the binary."""
    target = user_config()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print(f"конфиг уже есть: {target}")
        return
    if not DEVICE_JSON.exists():
        print("конфиг не установлен: создайте его командой")
        print("  hiper init --id <id> --key <key> --ip <ip>")
        return
    copy_with_retry(DEVICE_JSON, target)
    print(f"конфиг: {target}")


def install() -> Path:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            sys.exit("Не задан LOCALAPPDATA")
        target_dir = Path(local) / "Programs" / "hiper"
    else:
        target_dir = Path.home() / ".local" / "bin"

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / EXE_NAME
    copy_with_retry(EXE, target)
    if os.name != "nt":
        target.chmod(0o755)
    print(f"установлено: {target}")
    install_config()

    if os.name != "nt":
        path_env = os.environ.get("PATH", "")
        if str(target_dir) not in path_env.split(":"):
            print(f"добавьте в PATH: export PATH=\"$HOME/.local/bin:$PATH\"")
        return target

    # Пользовательский PATH (без прав администратора)
    key = winreg_path()
    current = read_user_path(key)
    if str(target_dir).lower() not in [p.lower() for p in current.split(os.pathsep) if p]:
        new_path = os.pathsep.join([p for p in current.split(os.pathsep) if p] + [str(target_dir)])
        write_user_path(key, new_path)
        print(f"PATH обновлён: добавлен {target_dir}")
        print("Перезапустите терминал, чтобы команда 'hiper' стала доступна.")
    else:
        print(f"PATH уже содержит {target_dir}")
    return target


def winreg_path():
    import winreg

    return winreg


def read_user_path(winreg) -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, "Path")[0]
    except FileNotFoundError:
        return ""


def write_user_path(winreg, value: str) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка hiper.exe")
    parser.add_argument("--install", action="store_true", help="установить в PATH")
    parser.add_argument("--reset-config", action="store_true", help="пересоздать device.json")
    args = parser.parse_args()

    if args.reset_config and DEVICE_JSON.exists():
        DEVICE_JSON.unlink()

    prepare_device()
    build()

    if args.install:
        install()
    else:
        print(f"\nУстановить в PATH: python build.py --install")
        print(f"Или запускать напрямую: {EXE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
