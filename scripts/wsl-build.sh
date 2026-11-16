#!/usr/bin/env bash
# Сборка Linux-бинарника hiper внутри WSL и установка в ~/.local/bin.
# Запуск: wsl -e bash /mnt/d/Programming/hiper-cli/scripts/wsl-build.sh
set -euo pipefail

SRC="${SRC:-/mnt/d/Programming/hiper-cli}"
BUILD_DIR="${HOME}/.cache/hiper-build"
PREFIX_DIR="${HOME}/.local"

echo "== 1. pip =="
if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "pip не найден, ставлю в пользовательский каталог"
    python3 - <<'PY'
import urllib.request, pathlib
target = pathlib.Path("/tmp/get-pip.py")
urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", target)
print("скачано:", target, target.stat().st_size, "байт")
PY
    python3 /tmp/get-pip.py --user --break-system-packages 2>&1 | tail -3
fi

export PATH="${PREFIX_DIR}/bin:${PATH}"
python3 -m pip --version

echo "== 2. зависимости =="
python3 -m pip install --user --break-system-packages --quiet --upgrade pyinstaller tinytuya
python3 -c "import tinytuya, PyInstaller; print('tinytuya', tinytuya.__version__, '| pyinstaller', PyInstaller.__version__)"

echo "== 3. подготовка =="
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"
cp "${SRC}/hiper.py" "${SRC}/shell_ui.py" "${SRC}/device.json" "${BUILD_DIR}/"
echo "файлы: $(ls -1 "${BUILD_DIR}" | tr '\n' ' ')"

echo "== 4. сборка =="
cd "${BUILD_DIR}"
python3 -m PyInstaller \
    --onefile \
    --console \
    --name hiper \
    --collect-all tinytuya \
    --add-data "device.json:." \
    --noconfirm \
    --clean \
    --log-level WARN \
    hiper.py 2>&1 | tail -15

if [ ! -f "${BUILD_DIR}/dist/hiper" ]; then
    echo "СБОРКА НЕ УДАЛАСЬ: нет ${BUILD_DIR}/dist/hiper" >&2
    exit 1
fi

echo "== 5. установка =="
mkdir -p "${PREFIX_DIR}/bin"
install -m 755 "${BUILD_DIR}/dist/hiper" "${PREFIX_DIR}/bin/hiper"
echo "бинарник: $(file -b "${PREFIX_DIR}/bin/hiper")"
echo "размер  : $(du -h "${PREFIX_DIR}/bin/hiper" | cut -f1)"

echo "== 6. проверка =="
"${PREFIX_DIR}/bin/hiper" --version
echo
echo "Готово. Убедитесь, что ${PREFIX_DIR}/bin есть в PATH:"
grep -q '.local/bin' "${HOME}/.bashrc" 2>/dev/null && echo "  PATH настроен в ~/.bashrc" \
    || echo "  добавьте: echo 'export PATH=\$HOME/.local/bin:\$PATH' >> ~/.bashrc"
