# hiper

> **Авторство:** код в этом репозитории написан AI-агентом (OpenCode,
> DeepSeek V4.1 Flash) по заданию владельца и проверен владельцем на реальной
> лампе. Подробнее: [Как это сделано](#как-это-сделано) и
> [AUTHORS.md](AUTHORS.md).

Локальный CLI и интерактивная консоль для лампы **Hiper IoT A61 RGB**.
Всё работает по локальному протоколу Tuya 3.3 на TCP 6668 — без облака,
аккаунта, фирменного приложения и интернета. Лампе достаточно быть в той же
Wi-Fi сети.

```
$ hiper status
on  mode=colour brightness=55% (554, colour) temp=6500K colour=h354 s1000 v1000

$ hiper set color 255 0 25
colour: #ff0019 -> h=354 s=1000 v=1000
```

Запуск `hiper` без аргументов открывает гостевую консоль, похожую на шелл самой
лампы: busybox-подобные команды, `neofetch` с логотипом Tuya и эмулированный
`/proc`. Управление лампой в ней настоящее, системные команды — декорация.

---

## Как это сделано

Проект **написан AI-агентом** (OpenCode, модель DeepSeek V4.1 Flash) по
техническому заданию владельца репозитория. Требования, устройство, набор
команд, поведение консоли и платформы сборки задал владелец; код, документацию
и скрипты сборки написал агент. Владелец проверял каждый шаг на реальной лампе.

---

## Требования

| Платформа | Что нужно |
|---|---|
| Windows | Python 3.9+, `tinytuya`, `pyinstaller` (только для сборки exe) |
| Linux / WSL | Python 3.9+, `tinytuya`, `pip` |
| Termux (Android) | Python, `tinytuya` |

Лампа должна быть доступна по постоянному IP в локальной сети. Настоятельно
рекомендуется закрепить адрес на роутере; если он изменился, `hiper rescan`
найдёт лампу заново.

---

## Как получить `local_key`

Лампа не отдаёт локальный ключ по сети. Бесплатный аккаунт Tuya IoT Platform
нужен **один раз**, только чтобы прочитать ключ; дальше облако не участвует.

1. Создайте аккаунт на <https://iot.tuya.com> и Cloud-проект (регион
   **Central Europe** для EU-устройств). Запомните *Access ID* и
   *Access Secret*.
2. В *Devices → Link Tuya App Account* отсканируйте QR-код приложением
   **Smart Life**. Фирменное приложение Hiper IoT не привязывается к IoT
   Platform, поэтому лампу сначала нужно перепривязать в Smart Life.
3. В *API Explorer / Device Management* возьмите `id` устройства и
   `local_key`.
4. Создайте конфиг:

   ```bash
   hiper init --id <device-id> --key <local-key> --ip <lamp-ip>
   ```

   или импортируйте готовый файл `tinytuya`:

   ```bash
   hiper init --from devices.json
   ```

`hiper init` сохраняет конфиг и сразу пробует прочитать лампу — так вы сразу
увидите, верны ли ключ и IP. Перепривязка лампы в приложении выдаёт **новый**
ключ — после неё запустите `init` снова.

---

## Конфигурация

Конфиг устройства **всегда снаружи**. Он не вкомпилирован в бинарник; exe лишь
знает, где его искать.

Порядок поиска:

1. `--config <путь>`
2. переменная окружения `HIPER_CONFIG`
3. `%LOCALAPPDATA%\hiper\hiper.json` (Windows) или
   `~/.config/hiper/hiper.json` (Linux, WSL, Termux)
4. `~/.hiper/hiper.json`
5. `hiper.json` рядом с exe
6. `hiper.json` в текущем каталоге

Переменные окружения: `HIPER_ID`, `HIPER_KEY`, `HIPER_IP`,
`HIPER_VERSION`, `HIPER_LANG`.

```json
{
    "name": "Hiper IoT A61 RGB",
    "id": "<device-id>",
    "key": "<local_key>",
    "ip": "192.168.1.50",
    "version": "3.3",
    "lang": "ru",
    "kelvin_min": 2700,
    "kelvin_max": 6500
}
```

---

## Команды

```bash
hiper on
hiper off
hiper toggle
hiper status [--json]

hiper mode set color|white|scene|music   # "colour" то же, что "color"

hiper set bright 1-100          # проценты
hiper set temp 1000-6000        # кельвины, обрезаются по диапазону лампы
hiper set color 255 0 25        # R G B, 0-255
hiper set color "#ff0019"       # или hex

hiper gradient "(255,0,0)" "(0,0,255)"           # переход за 2 с
hiper gradient "(255,0,0)" "(0,0,255)" --loop 0  # бесконечно, Ctrl+C
hiper gradient "#ff0000" "#0000ff" --pingpong

hiper raw 22 800                # записать сырой DP

hiper reboot                    # самопроверка и возврат к прежнему режиму
hiper reboot --off 4            # держать лампу выключенной 4 с в начале

hiper init --id <id> --key <key> --ip <ip>
hiper init --from devices.json
hiper rescan                    # найти лампу заново при смене IP
hiper info                      # сводка конфига, ключ замаскирован

hiper --lang en                 # разовый переключатель языка
hiper shell                     # консоль (то же, что без аргументов)
```

Коды возврата: `0` успех, `1` ошибка, `130` прервано.

`hiper status --json` печатает сырые datapoint'ы — удобно для скриптов:

```bash
hiper status --json | jq -r ".[\"20\"]"
```

### Градиент

`gradient` принимает два цвета в любом виде:

```bash
hiper gradient "(255,0,0)" "(0,0,255)"
hiper gradient "#ff0000" "#0000ff"
hiper gradient 255 0 0 0 0 255
```

Опции: `--steps N` (кадры, по умолчанию 24), `--duration S` (по умолчанию 2),
`--loop N` (`0` — бесконечно), `--pingpong`.

Лампа подтверждает примерно 16 кадров в секунду, поэтому очень короткий
`--duration` округляется вверх; анимация всегда заканчивается точно на втором
цвете.

---

## Интерактивная консоль

```
Hiper IoT A61 RGB - on, 55%, 6500K, h354, to exit type 'exit'. Help - hiper help
──────────────────────────────────────────────────────────────

root@tuya-a61:/home/root$
```

- **Tab** дополняет команды, затем их аргументы (`set ` → `bright temp
  color`, `mode set ` → режимы, `lang ` → языки, пути для `cd`/`cat`/`ls`).
- **↑ / ↓** листают историю; `history` печатает её.
- `help` — список, `help <команда>` — справка по одной.
- `lang en|ru` переключает язык интерфейса (по умолчанию **английский**),
  выбор сохраняется в конфиге.

Команды лампы: `status`, `on`, `off`, `toggle`, `set bright|temp|color`,
`mode set`, `gradient`, `raw`, `info`.

Эмулированная система: `uname`, `hostname`, `whoami`, `id`, `pwd`, `cd`, `ls`,
`cat`, `echo`, `date`, `uptime`, `free`, `df`, `ps`, `dmesg`, `ifconfig`,
`wifi`, `reboot` (самопроверка), `poweroff` (отказывает), `sudo` (вы уже root).

`free`, `df`, `ps`, `neofetch` и `/proc` показывают **вымышленное** устройство:
8 MiB RAM, 12 MiB flash, BK7231N. Это часть шутки, реальная лампа другая.

`neofetch` / `fastfetch` рисует оранжевый логотип Tuya рядом со сводкой.

`reboot` — единственная системная команда, которая делает что-то физическое:
сохраняет текущее состояние, выключает лампу на 2 с, включает, прогоняет
красный/зелёный/синий, яркость белого 1–100 % и температуру 2700–6500 K,
сверяет каждый шаг с реальным ответом лампы, мигает дважды и возвращает
сохранённые режим, цвет, яркость и состояние выключателя. В отчёте видно,
сколько проверок совпало; `--off N` меняет начальную паузу. `poweroff`
по-прежнему отказывает — это только декорация.

Настоящая сеть:

- `ping [-c N] <host>` вызывает системный `ping`.
- `curl [-I] <url>` делает реальный HTTP-запрос через `urllib` (внешний
  `curl` не нужен).
- `ssh` и `telnet` честно проверяют порт и сообщают, что на лампе **нет
  sshd/telnetd** — единственный сервис это Tuya на TCP 6668.

Вывод системных команд остаётся английским, как на настоящем шелле устройства;
переводится только собственный интерфейс утилиты.

---

## Установка

### Windows — один .exe

```powershell
cd hiper-cli
python -m pip install tinytuya pyinstaller
python build.py --install
```

`build.py`:

1. берёт ключ из `..\tuya-lamp\devices.json` (или из готового `device.json`),
2. собирает однофайловый `dist\hiper.exe` (около 15 МБ),
3. копирует его в `%LOCALAPPDATA%\Programs\hiper` и добавляет папку в
   пользовательский `PATH`,
4. копирует конфиг устройства в `%LOCALAPPDATA%\hiper\hiper.json`.

**Перезапустите терминал** после установки, иначе `hiper` не найдётся.
Конфиг не вшит в exe: замените `hiper.json`, и тот же бинарник будет
обслуживать другую лампу.

### Linux / WSL без root

```bash
bash scripts/wsl-install.sh
```

Ставит `tinytuya` через `pip --user`, копирует модули в `~/.local/lib/hiper`,
пишет лаунчер в `~/.local/bin/hiper`, кладёт конфиг в
`~/.config/hiper/hiper.json` и добавляет `~/.local/bin` в `PATH`. `sudo` не
нужен.

Настоящую ELF-сборку тоже можно сделать, но PyInstaller требует разделяемую
библиотеку Python (`sudo apt install libpython3.x`); скрипт
`scripts/wsl-build.sh` пригодится, когда этот пакет появится.

### Termux

```bash
bash scripts/termux-install.sh
```

PyInstaller не работает на Android/Termux, поэтому скрипт ставит hiper как
Python-пакет с лаунчером в `$PREFIX/bin/hiper`.

### Из исходников где угодно

```bash
python -m pip install tinytuya
python hiper.py status
```

или установка пакетом:

```bash
python -m pip install .
hiper status
```

---

## Особенности прошивки

Заложены в код, но важны при доработке:

1. **Один DP на пакет.** Если два datapoint'а приходят в одном пакете,
   прошивка молча теряет один. hiper шлёт их по одному с паузой 250 мс.
2. **`colour_data` — hex, а не JSON**: `hHHHssssvvvv` — hue 0–360,
   насыщенность и яркость 0–1000. Tuya документирует DP как JSON, но эта
   лампа передаёт 12 hex-символов.
3. **Яркость начинается с 10**, поэтому `set bright 0` даёт 10 (≈1 %).
4. **Переход в режим `colour` сбрасывает яркость** к дефолту прошивки
   (~587). Сначала задайте цвет, потом яркость.
5. **`DP22` — яркость белого канала.** В цветовом режиме настоящая яркость
   лежит в поле `v` у `colour_data`, а `DP22` хранит старое значение. hiper
   сам читает и пишет нужный канал.
6. `music_data` / `control_data` используют s/v в диапазоне 0–255, в отличие
   от `colour_data` (0–1000).

Карта datapoint'ов:

| DP | Что | Значения |
|---|---|---|
| 20 | выключатель | `true` / `false` |
| 21 | режим | `white`, `colour`, `scene`, `music` |
| 22 | яркость белого | 10–1000 |
| 23 | цветовая температура | 0–1000 (2700–6500 K) |
| 24 | цвет | `hHHHssssvvvv` |
| 25 | сцена | 12 байт hex |
| 26 | таймер | секунды |

---

## Безопасность

`local_key` — фактически пароль от лампы. Он лежит только во внешнем конфиге,
маскируется в `hiper info` и не должен попадать в репозиторий. Соль проекта та
же, что и у лампы: любой в вашей LAN с ключом может ею управлять.

`.gitignore` исключает `device.json`, `hiper.json`, `dist/`, `build/`, `*.spec`
и `__pycache__/`.

---

## Лицензия

MIT — см. [LICENSE](LICENSE).

English documentation: [README.md](README.md).
