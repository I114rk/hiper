#!/usr/bin/env bash
# Install hiper into WSL/Debian without root (pip --user + launcher).
#
#   wsl -e bash /mnt/d/Programming/hiper-cli/scripts/wsl-install.sh
#
# Works without sudo: only user site-packages and ~/.local are touched.
set -euo pipefail

SRC="${SRC:-/mnt/d/Programming/hiper-cli}"
LIB_DIR="${HOME}/.local/lib/hiper"
BIN_DIR="${HOME}/.local/bin"
CFG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/hiper"

echo "== 1. pip =="
if ! python3 -m pip --version >/dev/null 2>&1; then
    python3 - <<'PY'
import pathlib
import urllib.request

target = pathlib.Path("/tmp/get-pip.py")
urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", target)
print("downloaded:", target)
PY
    python3 /tmp/get-pip.py --user --break-system-packages 2>&1 | tail -2
fi
export PATH="${BIN_DIR}:${PATH}"

echo "== 2. tinytuya =="
python3 -m pip install --user --break-system-packages --quiet --upgrade tinytuya
python3 -c "import tinytuya; print('tinytuya', tinytuya.__version__)"

echo "== 3. files =="
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

echo "== 4. launcher =="
cat > "${BIN_DIR}/hiper" <<'LAUNCHER'
#!/usr/bin/env bash
exec python3 "${HOME}/.local/lib/hiper/hiper.py" "$@"
LAUNCHER
chmod 755 "${BIN_DIR}/hiper"
echo "${BIN_DIR}/hiper"

echo "== 5. PATH =="
if ! grep -q 'HOME/.local/bin' "${HOME}/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
    echo "added to ~/.bashrc"
else
    echo "already in ~/.bashrc"
fi

echo "== 6. check =="
"${BIN_DIR}/hiper" --version
"${BIN_DIR}/hiper" info || true
"${BIN_DIR}/hiper" status || echo "(lamp unreachable from this session - normal in WSL NAT mode)"
echo
echo "Done. Open a new WSL terminal and type: hiper"
