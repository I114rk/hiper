#!/data/data/com.termux/files/usr/bin/bash
# Install hiper in Termux (Android, aarch64).
#
#   bash termux-install.sh
#
# PyInstaller does not work on Termux (no glibc, no Android bootloader support),
# so hiper is installed as a plain Python package with a launcher script.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB_DIR="${PREFIX}/lib/hiper"
BIN_DIR="${PREFIX}/bin"
CFG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/hiper"

echo "== 1. dependencies =="
pkg install -y python >/dev/null 2>&1 || true
python -m pip install --quiet --upgrade pip
python -m pip install --quiet --upgrade tinytuya
python -c "import tinytuya; print('tinytuya', tinytuya.__version__)"

echo "== 2. files =="
mkdir -p "${LIB_DIR}" "${BIN_DIR}" "${CFG_DIR}"
cp "${SRC}/hiper.py" "${SRC}/shell_ui.py" "${SRC}/i18n.py" "${SRC}/lineedit.py" "${LIB_DIR}/"
echo "code -> ${LIB_DIR}"

# Device config stays external: it is never baked into the code.
if [ -f "${CFG_DIR}/hiper.json" ]; then
    echo "config already present: ${CFG_DIR}/hiper.json"
elif [ -f "${SRC}/device.json" ]; then
    cp "${SRC}/device.json" "${CFG_DIR}/hiper.json"
    echo "config -> ${CFG_DIR}/hiper.json"
else
    echo "no config yet: run 'hiper init --id <id> --key <key> --ip <ip>'"
fi

echo "== 3. launcher =="
cat > "${BIN_DIR}/hiper" <<'LAUNCHER'
#!/data/data/com.termux/files/usr/bin/bash
exec python "${PREFIX}/lib/hiper/hiper.py" "$@"
LAUNCHER
chmod 755 "${BIN_DIR}/hiper"

echo "== 4. check =="
hiper --version
hiper info || true
echo
echo "Done. The 'hiper' command is available in Termux."
echo "If the lamp is on another network, fix ip in ${CFG_DIR}/hiper.json"
