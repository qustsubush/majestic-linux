
# majestic-linux

Скрипт для запуска и игры на замечательном проекте Majestic RP на базе Grand Theft Auto 5



## 🚀Установка и запуск

Установка и запуск происходят следующим образом (установку следует выполнять из домашней директории):

```bash
mkdir -p majestic-linux
curl -fSL -o majestic-linux/majestic-linux https://github.com/qustsubush/majestic-linux/releases/latest/download/majestic-linux
chmod +x majestic-linux/majestic-linux
  
  # Запуск
./majestic-linux/majestic-linux
```

Следуйте инструкциям внутри скрипта. В случае возникновения проблем можете связаться со мной в Discord: qustsu

## ❔FaQ (ЧАВО)
<details>
  <summary>При нажатии клавиши WIN происходят рандомные действия в игре</summary>

Это очень просто решается.

1. Запустите protontricks удобным для вайс способом (Не FlatPak версию!)
2. Выберите из списка "Gtand Theft Auto 5 Legacy: 271590"
3. Из следующего списка выберите "Select the default wineprefix"
4. Выберите "Run explorer"
5. Нажмите на "My Computer", затем перейдите по пути C:\Program Files\Rockstar Games\Launcher
6. Запустите Launcher.exe
7. После авторизации в Social Club перейдите в настройки и отключите пункт "Отключать клавишу Windows". После отключения проблема исчезнет

Решение проблемы взято с Discrod сервера Majestic-RP-Linux-Runner

</details>

<details>
  <summary>Появляются артефакты на интерфейсе</summary>

Для решения проблемы нужно выключить CEF в настройказ мультиплеера

1. Откройте конфигурационный файл мультиплеера
```bash
# Используйте любой другой установленный у вас текстовый редактор
nano ~/.local/share/Steam/steamapps/compatdata/271590/pfx/drive_c/users/steamuser/AppData/Roaming/majestic-launcher/Multiplayer/majestic.json
```
2. Измените параметр `cefUseHardwareAcceleration` с `true` на `false`

Решение проблемы взято с Discrod сервера Majestic-RP-Linux-Runner

</details>

<details>
  <summary>Хочу установить ярлык в главном меню (Пуск)</summary>

Чтобы поставить ярлык нужно создать файл в директории пользовательских ярлыков.
1. Создайте файл .desktop в ~/.local/share/applications/ через Ваш текстовый редактор
~~~bash
# Название файла не влияет на название ярлыка
nano ~/.local/share/applications/majestic.desktop
~~~
2. Внутри файла нужно вставить этот текст:
```txt
[Desktop Entry]
# Название ярkыка
Name=Majestic Launcher - Linux
Comment=Majestic Launcher
# Указываете в ковычках путь до скрипта
Exec=bash -c '"$HOME/majestic-linux/majestic-linux"'
# Иконка ярлыка
Icon=steam_icon_271590
Terminal=true
Type=Application
Categories=Game;
```
3. Сохраняете файл и проверяете ярлык

</details>

## ☕ Поддержать проект

Если этот инструмент оказался для вас полезным, вы можете поддержать его разработку. Любая сумма помогает уделять больше времени улучшению проекта и исправлению багов.

- [Donatty](https://donatty.com/qustsubush)
## 🙏 Особая благодарность
- [majestic-rp-linux-runner](https://github.com/digitalhorizongroup/majestic-rp-linux) - помог в исследовании прицнципа работы majestic лаунчера.
