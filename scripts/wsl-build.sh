#!/usr/bin/env bash
# Build a single Linux ELF for hiper inside WSL and install it to ~/.local/bin.
#
#   wsl -e bash /mnt/d/Programming/hiper-cli/scripts/wsl-build.sh
#
# PyInstaller needs the Python shared library. Debian 13 ships Python 3.13 but
# the libpython3.13 package may be missing; this script installs it with sudo
# when possible and refuses to run without root otherwise.
set -euo pipefail

SRC="${SRC:-/mnt/d/Programming/hiper-cli}"
BUILD_DIR="${HOME}/.cache/hiper-build"
PREFIX_DIR="${HOME}/.local"
CFG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/hiper"

echo "== 1. python =="
python3 -c 'import sys; print("python", sys.version.split()[0])'

echo "== 2. shared library =="
PYVER="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
LIBCANDIDATES=(libpython3.so "libpython${PYVER}.so" "libpython${PYVER}.so.1.0")
FOUND=""
for candidate in "${LIBCANDIDATES[@]}"; do
    if ldconfig -p 2>/dev/null | grep -q "${candidate//./\\.}"; then
        FOUND="${candidate}"
        break
    fi
done

if [ -z "${FOUND}" ]; then
    echo "libpython${PYVER} not found, trying: sudo apt-get install -y libpython${PYVER}"
    if ! command -v sudo >/dev/null || ! sudo -n true 2>/dev/null; then
        echo "СБОРКА НЕ УДАЛАСЬ: нужны root-права. Пакет libpython${PYVER} не установлен." >&2
        echo "  sudo apt-get install -y libpython${PYVER}" >&2
        exit 1
    fi
    sudo apt-get update -qq
    sudo apt-get install -y "libpython${PYVER}"
    FOUND="libpython${PYVER}.so.1.0"
fi
echo "shared library: ${FOUND}"

echo "== 3. pip =="
if ! python3 -m pip --version >/dev/null 2>&1; then
    python3 - <<'PY'
import pathlib
import urllib.request

target = pathlib.Path("/tmp/get-pip.py")
urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", target)
print("downloaded:", target, target.stat().st_size, "bytes")
PY
    python3 /tmp/get-pip.py --user --break-system-packages 2>&1 | tail -3
fi

export PATH="${PREFIX_DIR}/bin:${PATH}"

echo "== 4. dependencies =="
python3 -m pip install --user --break-system-packages --quiet --upgrade pyinstaller tinytuya
python3 -c "import tinytuya, PyInstaller; print('tinytuya', tinytuya.__version__, '| pyinstaller', PyInstaller.__version__)"

echo "== 5. staging (no secrets) =="
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"
cp "${SRC}/hiper.py" "${SRC}/shell_ui.py" "${SRC}/i18n.py" "${SRC}/lineedit.py" "${BUILD_DIR}/"

if [ -f "${SRC}/device.json" ]; then
    cp "${SRC}/device.json" "${BUILD_DIR}/hiper.json"
    echo "staged: code + device config (the binary does not embed it)"
else
    echo "staged: code only (no device.json in the source tree)"
fi

echo "== 6. build =="
cd "${BUILD_DIR}"
python3 -m PyInstaller \
    --onefile \
    --console \
    --name hiper \
    --collect-all tinytuya \
    --noconfirm \
    --clean \
    --log-level WARN \
    hiper.py 2>&1 | tail -15

if [ ! -f "${BUILD_DIR}/dist/hiper" ]; then
    echo "СБОРКА НЕ УДАЛАСЬ: нет ${BUILD_DIR}/dist/hiper" >&2
    exit 1
fi

echo "== 7. install =="
mkdir -p "${PREFIX_DIR}/bin" "${CFG_DIR}"
install -m 755 "${BUILD_DIR}/dist/hiper" "${PREFIX_DIR}/bin/hiper"
echo "binary: $(file -b "${PREFIX_DIR}/bin/hiper")"
echo "size  : $(du -h "${PREFIX_DIR}/bin/hiper" | cut -f1)"

# Device config stays external: it is never baked into the binary.
if [ -f "${CFG_DIR}/hiper.json" ]; then
    echo "config already present: ${CFG_DIR}/hiper.json"
elif [ -f "${BUILD_DIR}/hiper.json" ]; then
    cp "${BUILD_DIR}/hiper.json" "${CFG_DIR}/hiper.json"
    echo "config -> ${CFG_DIR}/hiper.json"
else
    echo "no config yet: run 'hiper init --id <id> --key <key> --ip <ip>'"
fi

echo "== 8. check =="
"${PREFIX_DIR}/bin/hiper" --version
"${PREFIX_DIR}/bin/hiper" info || true
"${PREFIX_DIR}/bin/hiper" status || echo "(lamp unreachable from this session - normal in WSL NAT mode)"
echo
echo "Done. Open a new WSL terminal and type: hiper"
