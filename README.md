# Majestic Linux

Графическое приложение для установки, патчей и запуска лаунчера Majestic RP на Linux.

Приложение само подготавливает всё необходимое: патчит Proton, ставит нужные компоненты в префикс GTA V, устанавливает лаунчер Majestic и запускает его.

> Ветка `legacy` содержит предыдущую скриптовую версию проекта.

## ✨ Возможности

- Установка в один клик: все шаги выполняются автоматически, прогресс виден в разделе «Установка»
- Пропатченная копия Proton Experimental (`Proton Experimental (MJLX RCX fix)`), оригинальный Proton не изменяется
- Установка PowerShell в префикс игры и самого лаунчера Majestic
- Исправление обработчика `steam://` и установка цветного шрифта эмодзи
- Фикс ввода русских букв в игре
- Запуск лаунчера с произвольными аргументами, по умолчанию `-disable-gpu`
- Ярлык в меню приложений с иконкой
- Интерфейс на русском и английском

## 📋 Требования

- Linux с установленным Steam (не Flatpak-версия)
- Grand Theft Auto V, установленная через Steam и хотя бы один раз запущенная (так создаётся префикс `271590`)
- Proton Experimental, установленный в Steam
- `protontricks` (не Flatpak-версия)
- `gcc` для сборки шима с фиксом русской раскладки

Если каких-то пакетов не хватает, приложение покажет команду для вашего пакетного менеджера. После её выполнения установка продолжится автоматически.

## 🚀 Установка и запуск

### Готовый бинарник

```bash
mkdir -p ~/majestic-linux
curl -fSL -o ~/majestic-linux/majestic-rp-linux https://github.com/qustsubush/majestic-linux/releases/latest/download/majestic-rp-linux
chmod +x ~/majestic-linux/majestic-rp-linux
~/majestic-linux/majestic-rp-linux
```

### Из исходников

Нужны Python 3 и `pip`.

```bash
git clone https://github.com/qustsubush/majestic-linux.git
cd majestic-linux
./build
./dist/majestic-rp-linux
```

Скрипт `build` создаёт виртуальное окружение `.venv`, ставит зависимости и собирает один исполняемый файл через PyInstaller.

Для запуска без сборки:

```bash
python3 -m venv .venv
.venv/bin/pip install -r src/requirements.txt
.venv/bin/python src/app/app.py
```

## 🧭 Как пользоваться

1. Откройте раздел **«Установка»** и нажмите **«Установить»**. Если приложение попросит пакеты, выполните показанную команду в терминале.
2. Дождитесь, пока все шаги получат отметку ✓.
3. Перейдите в раздел **«Главная»** и нажмите **«Играть»**.

### Разделы

| Раздел | Что внутри |
| --- | --- |
| Главная | Запуск и остановка лаунчера, вывод и логи |
| Установка | Шаги установки, список недостающих пакетов |
| Настройки | Язык интерфейса, путь к установщику лаунчера, аргументы запуска |
| Дополнительно | Создание ярлыка в меню приложений |
| О программе | Версия и ссылка на GitHub |

### Логи

Логи сессий хранятся в `~/.local/state/majesticrplinux/logs`. Открыть папку можно кнопкой **«Открыть папку логов»** на главной странице. Лог текущей сессии копируется кнопкой **«Копировать лог»**.

## ❔ FAQ (ЧАВО)

<details>
  <summary>При нажатии клавиши WIN происходят рандомные действия в игре</summary>

Это очень просто решается.

1. Запустите protontricks удобным для вас способом (не Flatpak-версию!)
2. Выберите из списка "Grand Theft Auto V Legacy: 271590"
3. Из следующего списка выберите "Select the default wineprefix"
4. Выберите "Run explorer"
5. Нажмите на "My Computer", затем перейдите по пути `C:\Program Files\Rockstar Games\Launcher`
6. Запустите `Launcher.exe`
7. После авторизации в Social Club перейдите в настройки и отключите пункт "Отключать клавишу Windows". После отключения проблема исчезнет

Решение проблемы взято с Discord-сервера Majestic-RP-Linux-Runner

</details>

<details>
  <summary>Появляются артефакты на интерфейсе</summary>

Для решения проблемы нужно выключить аппаратное ускорение CEF в настройках мультиплеера.

1. Откройте конфигурационный файл мультиплеера
```bash
nano ~/.local/share/Steam/steamapps/compatdata/271590/pfx/drive_c/users/steamuser/AppData/Roaming/majestic-launcher/Multiplayer/majestic.json
```
2. Измените параметр `cefUseHardwareAcceleration` с `true` на `false`

Решение проблемы взято с Discord-сервера Majestic-RP-Linux-Runner

</details>

<details>
  <summary>Хочу ярлык в главном меню (Пуск)</summary>

Откройте раздел **«Дополнительно»** и нажмите **«Создать ярлык для запуска»**. Ярлык «Majestic RP Linux» с иконкой появится в меню приложений.

</details>

<details>
  <summary>Не вводятся русские буквы в игре</summary>

Фикс входит в установку и применяется автоматически. Убедитесь, что шаг «Фикс русской раскладки» в разделе «Установка» отмечен ✓, и перезапустите игру. Для сборки шима нужен `gcc`.

</details>

## ☕ Поддержать проект

Если этот инструмент оказался для вас полезным, вы можете поддержать его разработку. Любая сумма помогает уделять больше времени улучшению проекта и исправлению багов.

- [Donatty](https://donatty.com/qustsubush)

## 💬 Связь

Если возникли проблемы, напишите в Discord: `qustsu`

## 🙏 Особая благодарность

- [majestic-rp-linux-runner](https://github.com/digitalhorizongroup/majestic-rp-linux) помог в исследовании принципа работы лаунчера Majestic.
- Emoji artwork: Twemoji (Twitter, Inc. and contributors), CC-BY 4.0; font: Mozilla twemoji-colr, Apache 2.0.
