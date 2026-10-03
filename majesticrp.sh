#!/bin/bash

set -euo pipefail

clear

APPID=271590

if ! grep -rql 'Grand Theft Auto V' \
    "$HOME/.steam/steam/steamapps"/*.acf \
    "$HOME/.local/share/Steam/steamapps"/*.acf 2>/dev/null; then
    echo "GTA 5 не найдена! Установите его через Steam"
    exit 1
fi

PKG="protontricks"

if command -v pacman &>/dev/null; then
    PM="pacman"
    CHECK_CMD=(pacman -Qi "$PKG")
    INSTALL_CMD=(sudo pacman -S --noconfirm "$PKG")
elif command -v dpkg &>/dev/null; then
    PM="apt"
    CHECK_CMD=(dpkg -s "$PKG")
    INSTALL_CMD=(sudo apt install -y "$PKG")
elif command -v rpm &>/dev/null; then
    PM="dnf"
    CHECK_CMD=(rpm -q "$PKG")
    INSTALL_CMD=(sudo dnf install -y "$PKG")
else
    echo "Пакет '$PKG' не установлен."
    echo "Не найден поддерживаемый пакетный менеджер (pacman, apt, dnf)."
    echo ""
    echo "Установите protontricks вручную."
    echo "Не рекомендуется использовать Flatpak-версию"
    exit 1
fi

if ! "${CHECK_CMD[@]}" &>/dev/null; then
    echo "Пакет '$PKG' не установлен."
    echo "Менеджер: $PM"
    read -rp "Установить? [Y/n] " answer

    case "${answer:-Y}" in
        [yY]|[yY][eE][sS]|"")
            echo "Устанавливаю '$PKG'..."
            if "${INSTALL_CMD[@]}"; then
                echo "Готово."
            else
                echo "Ошибка установки."
                exit 1
            fi
            ;;
        *)
            echo "Установка отменена."
            echo "Установите '$PKG' самостоятельно."
            echo "Лучше через обычный пакетный менеджер, а не Flatpak."
            exit 1
            ;;
    esac
fi

STEAM_ROOT="$HOME/.local/share/Steam"
[ -d "$STEAM_ROOT/steamapps" ] || STEAM_ROOT="$(readlink -f "$HOME/.steam/steam")"
PFX="$STEAM_ROOT/steamapps/compatdata/$APPID/pfx"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/majestic-linux"
mkdir -p "$DATA"

install_launcher() {
    echo "Установка powershell в префикс GTA 5 ($APPID)"
    protontricks "$APPID" powershell
    curl -fL -o "$DATA/MajesticLauncherSetup.exe" \
        "https://cdn.majestic-files.net/launcher/cis/MajesticLauncherSetup.exe"
    protontricks-launch --appid "$APPID" "$DATA/MajesticLauncherSetup.exe"
}

patch_prefix() {
    mkdir -p "$PFX/drive_c/majestic"

    # steam://run/<appid>/<аргументы> -> PlayGTAV.exe <аргументы> в этом же префиксе
    cat > "$PFX/drive_c/majestic/steam-run.bat" <<'EOF'
@echo off
set "GAMEARGS="
for /f "tokens=4 delims=/" %%a in ("%~1") do set "GAMEARGS=%%a"
cd /d "S:\steamapps\common\Grand Theft Auto V"
start "" PlayGTAV.exe %GAMEARGS%
EOF
    sed -i 's/$/\r/' "$PFX/drive_c/majestic/steam-run.bat"

    cat > "$PFX/drive_c/majestic/handler.reg" <<'EOF'
Windows Registry Editor Version 5.00

[HKEY_LOCAL_MACHINE\Software\Classes\steam]
@="URL:steam protocol"
"URL Protocol"=""

[HKEY_LOCAL_MACHINE\Software\Classes\steam\shell\open\command]
@="C:\\windows\\system32\\cmd.exe /c C:\\majestic\\steam-run.bat \"%1\""
EOF
    protontricks -c 'wine regedit "C:\\majestic\\handler.reg"' "$APPID"
}

run_launcher() {
    pgrep -x steam >/dev/null || { echo "Запустите Steam и войдите в аккаунт"; exit 1; }

    local PROTON="$STEAM_ROOT/steamapps/common/Proton - Experimental/proton"
    local GTA="$STEAM_ROOT/steamapps/common/Grand Theft Auto V"
    local LAUNCHER="$PFX/drive_c/users/steamuser/AppData/Local/MajesticLauncher/Majestic Launcher.exe"

    ln -sfn "$STEAM_ROOT" "$PFX/dosdevices/s:"

    STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT" \
    STEAM_COMPAT_DATA_PATH="$STEAM_ROOT/steamapps/compatdata/$APPID" \
    STEAM_COMPAT_INSTALL_PATH="$GTA" \
    STEAM_COMPAT_LIBRARY_PATHS="$STEAM_ROOT/steamapps" \
    STEAM_COMPAT_MOUNTS="$STEAM_ROOT" \
    STEAM_COMPAT_APP_ID="$APPID" \
    SteamAppId="$APPID" SteamGameId="$APPID" \
    "$PROTON" run "$LAUNCHER" --disable-gpu
}

echo "1) Установить лаунчер"
echo "2) Патч префикса"
echo "3) Запустить лаунчер"
read -rp "> " choice

case "$choice" in
    1) install_launcher ;;
    2) patch_prefix ;;
    3) run_launcher ;;
    *) echo "неизвестный вариант" ;;
esac