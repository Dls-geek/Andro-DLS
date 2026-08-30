"""
    COPYRIGHT DISCLAIMER

    Script : PhoneSploit Pro - All in One Android Hacking ADB Toolkit

    Copyright (C) 2026  Azeem Idrisi (github.com/AzeemIdrisi)

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

    Forking and modifying are allowed, but credit must be given to the
    original developer, [Azeem Idrisi (github.com/AzeemIdrisi)], and copying the code
    is not permitted without permission.

    For any queries, open an issue at : https://github.com/Dls-geek/PhoneSploit-Pro/issues
"""

version = "v2.1.1"

menu1 = """
    [bold yellow]── DLS-GEEK · PHONE CONTROL ─────────────────────────────────[/bold yellow]

    [white]1.[/white] [green]▸ AUTO CONNECT[/green]      [dim]USB → Wi-Fi bridge → payload → saved forever[/dim]
    [white]2.[/white] [green]▸ RECONNECT[/green]        [dim]saved phone → live shell + pentest options[/dim]
    [white]3.[/white] [green]▸ PORTMAP SETUP[/green]    [dim]permanent internet tunnel (one-time)[/dim]

    [dim]0. Exit          keeper: tunnel+listener 24/7 in background[/dim]
"""

_focused = "\n  [dim](focused build — legacy tools removed)[/dim]\n"
menu2 = _focused
menu3 = _focused
menu4 = _focused
menu5 = _focused

menu = [menu1, menu2, menu3, menu4, menu5]

banner2 = """
        ░█▀▀█ █──█ █▀▀█ █▀▀▄ █▀▀ ░█▀▀▀█ █▀▀█ █── █▀▀█ ─▀─ ▀▀█▀▀ 　 ░█▀▀█ █▀▀█ █▀▀█
        ░█▄▄█ █▀▀█ █──█ █──█ █▀▀ ─▀▀▀▄▄ █──█ █── █──█ ▀█▀ ──█── 　 ░█▄▄█ █▄▄▀ █──█
        ░█─── ▀──▀ ▀▀▀▀ ▀──▀ ▀▀▀ ░█▄▄▄█ █▀▀▀ ▀▀▀ ▀▀▀▀ ▀▀▀ ──▀── 　 ░█─── ▀─▀▀ ▀▀▀▀


            [red]{version}[/red]            [white]By github.com/Dls-geek[/white]
""".format(version=version)

banner3 = """
        █▀█ █░█ █▀█ █▄░█ █▀▀ █▀ █▀█ █░░ █▀█ █ ▀█▀   █▀█ █▀█ █▀█
        █▀▀ █▀█ █▄█ █░▀█ ██▄ ▄█ █▀▀ █▄▄ █▄█ █ ░█░   █▀▀ █▀▄ █▄█


            [red]{version}[/red]             [white]By github.com/Dls-geek[/white]
""".format(version=version)

banner4 = """
    _________.__                           _________      .__         .__  __    __________
    \\______  \\  |__   ____   ____  ____  /   _____/_____ |  |   ____ |__|/  |_  \\______   \\_______  ____
    |     ___/  |  \\ /  _ \\ /    \\_/ __ \\ \\_____  \\\\____ \\|  |  /  _ \\|  \\   __\\  |     ___/\\_  __ \\/  _ \\
    |    |   |   Y  (  <_> )   |  \\  ___/ /        \\  |_> >  |_(  <_> )  ||  |    |    |     |  | \\(  <_> )
    |____|   |___|  /\\____/|___|  /\\___  >_______  /   __/|____/\\____/|__||__|    |____|     |__|   \\____/
                  \\/            \\/     \\/        \\/ |__|


        [red]{version}[/red]                             [white]By github.com/Dls-geek[/white]
""".format(version=version)

banner5 = """
       ___  __                 ____     __     _ __     ___
      / _ \\/ /  ___  ___  ___ / __/__  / /__  (_) /_   / _ \\_______ 
     / ___/ _ \\/ _ \\/ _ \\/ -_)\\ \\/ _ \\/ / _ \\/ / __/  / ___/ __/ _ \\
    /_/  /_//_/\\___/_//_/\\__/___/ .__/_/\\___/_/\\__/  /_/  /_/  \\___/
                               /_/

        [red]{version}[/red]        [white]By github.com/Dls-geek[/white]
""".format(version=version)

banner6 = """
        ____  __                    _____       __      _ __       ____
       / __ \\/ /_  ____  ____  ___ / ___/____  / /___  (_) /_     / __ \\___________
      / /_/ / __ \\/ __ \\/ __ \\/ _ \\\\__ \\/ __ \\/ / __ \\/ / __/    / /_/ / ___/ __ \\
     / ____/ / / / /_/ / / / /  __/__/ / /_/ / / /_/ / / /_     / ____/ /  / /_/ /
    /_/   /_/ /_/\\____/_/ /_/\\___/____/ .___/_/\\____/_/\\__/    /_/   /_/   \\____/
                                     /_/

           [red]{version}[/red]               [white]By github.com/Dls-geek[/white]
""".format(version=version)

banner10 = """
     ____    __                              ____            ___               __        ____
    /\\  _`\\ /\\ \\                            /\\  _`\\         /\\_ \\           __/\\ \\__    /\\  _`\\
    \\ \\ \\L\\ \\ \\ \\___     ___     ___      __\\ \\,\\L\\_\\  _____\\//\\ \\     ___ /\\_\\ \\ ,_\\   \\ \\ \\L\\ \\_ __   ___
     \\ \\ ,__/\\ \\  _ `\\  / __`\\ /' _ `\\  /'__`\\/_\\__ \\ /\\ '__`\\\\\\ \\ \\   / __`\\/\\ \\ \\ \\/    \\ \\ ,__/\\`'__\\/ __`\\
      \\ \\ \\/  \\ \\ \\ \\ \\/\\ \\L\\ \\/\\ \\/\\ \\/\\  __/ /\\ \\L\\ \\ \\ \\L\\ \\\\_\\ \\_/\\ \\L\\ \\ \\ \\ \\ \\_    \\ \\ \\/\\ \\ \\//\\ \\L\\ \\
       \\ \\_\\   \\ \\_\\ \\_\\ \\____/\\ \\_\\ \\_\\ \\____\\\\ `\\____\\ \\ ,__//\\____\\ \\____/\\ \\_\\ \\__\\    \\ \\_\\ \\ \\_\\\\ \\____/
        \\/_/    \\/_/\\/_/\\/___/  \\/_/\\/_/\\/____/ \\/_____/\\ \\ \\/ \\/____/\\/___/  \\/_/\\/__/     \\/_/  \\/_/ \\/___/
                                                         \\ \\_\\
                                                          \\/_/

            [red]{version}[/red]                                [white]By github.com/Dls-geek[/white]
""".format(version=version)

banner11 = """
    _____________                   ________       ______     __________       ________
    ___  __ \\__  /_____________________  ___/__________  /________(_)_  /_      ___  __ \\____________
    __  /_/ /_  __ \\  __ \\_  __ \\  _ \\____ \\___  __ \\_  /_  __ \\_  /_  __/      __  /_/ /_  ___/  __ \\
    _  ____/_  / / / /_/ /  / / /  __/___/ /__  /_/ /  / / /_/ /  / / /_        _  ____/_  /   / /_/ /
    /_/     /_/ /_/\\____//_/ /_/\\___//____/ _  .___//_/  \\____//_/  \\__/        /_/     /_/    \\____/
                                            /_/


            [red]{version}[/red]                            [white]By github.com/Dls-geek[/white]
""".format(version=version)

banner12 = """
        ▒█▀▀█ █░░█ █▀▀█ █▀▀▄ █▀▀ ▒█▀▀▀█ █▀▀█ █░░ █▀▀█ ░▀░ ▀▀█▀▀ 　 ▒█▀▀█ █▀▀█ █▀▀█
        ▒█▄▄█ █▀▀█ █░░█ █░░█ █▀▀ ░▀▀▀▄▄ █░░█ █░░ █░░█ ▀█▀ ░░█░░ 　 ▒█▄▄█ █▄▄▀ █░░█
        ▒█░░░ ▀░░▀ ▀▀▀▀ ▀░░▀ ▀▀▀ ▒█▄▄▄█ █▀▀▀ ▀▀▀ ▀▀▀▀ ▀▀▀ ░░▀░░ 　 ▒█░░░ ▀░▀▀ ▀▀▀▀


            [red]{version}[/red]                            [white]By github.com/Dls-geek[/white]
""".format(version=version)

banner_list = [
    banner2,
    banner3,
    banner4,
    banner5,
    banner6,
    banner10,
    banner11,
    banner12,
]

instructions_banner = """[cyan]
        ____           __                  __  _
       /  _/___  _____/ /________  _______/ /(_)___  ____  _____
       / // __ \\/ ___/ __/ ___/ / / / ___/ __/ / __ \\/ __ \\/ ___/
     _/ // / / (__  ) /_/ /  / /_/ / /__/ /_/ / /_/ / / / (__  )
    /___/_/ /_/____/\\__/_/   \\__,_/\\___/\\__/_/\\____/_/ /_/____/
[/cyan]"""

hacking_banner = """[green]
    █░█ ▄▀█ █▀▀ █▄▀ █ █▄░█ █▀▀ ░ ░ ░
    █▀█ █▀█ █▄▄ █░█ █ █░▀█ █▄█ ▄ ▄ ▄
[/green]"""

keycode_menu = """
    [white]1. [green]Keyboard Text Input                [white]11. [green]Enter
    [white]2. [green]Home                               [white]12. [green]Volume Up
    [white]3. [green]Back                               [white]13. [green]Volume Down
    [white]4. [green]Recent Apps                        [white]14. [green]Media Play
    [white]5. [green]Power Button                       [white]15. [green]Media Pause
    [white]6. [green]DPAD Up                            [white]16. [green]Tab
    [white]7. [green]DPAD Down                          [white]17. [green]Esc
    [white]8. [green]DPAD Left
    [white]9. [green]DPAD Right
   [white]10. [green]Delete/Backspace[/green]
"""
