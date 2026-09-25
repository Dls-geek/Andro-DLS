# Andro-DLS — Banner & Menu System
# Copyright (c) 2025–2026 Khurshid Jhon & Dls-geek Team

version = "v3.0.0"

# ─── Banner (clean header, no broken box) ────────────────────────────────

banner = """
    █████╗ ██╗  ██╗ ██████╗ ██╗   ██╗██╗███╗   ██╗███████╗
   ██╔══██╗██║  ██║██╔═══██╗██║   ██║██║████╗  ██║██╔════╝
   ███████║███████║██║   ██║██║   ██║██║████╗ ██║█████╗
   ██══██║╚════██║██║   ██║╚██╗ ██╔╝██║██║╚██╗██║██╔══╝
   ██║  ██║     ██║██████╔╝ ╚████╝ ██║██║ ╚████║███████╗
   ╚═╝  ╚═╝     ═╝ ╚═════╝   ╚═══╝  ╚═╝╚═╝  ╚═══╝╚══════╝

           {version}  │  By Khurshid Jhon & Dls-geek Team

────────────────────────────────────────────────────────────────
""".format(version=version)

banner_list = [banner]

# ─── Menus ──────────────────────────────────────────────────────────────

menu1 = """
    [bold white]── ANDRO-DLS · PHONE CONTROL ─────────────────────────────────[/bold white]

    [dim]1.[/dim] [white]USB SETUP[/white]              [dim]cable → tcpip 5555 → wireless[/dim]
    [dim]2.[/dim] [white]CONNECTED DEVICES[/white]     [dim]see all · reconnect · manage[/dim]
    [dim]3.[/dim] [white]BUILD AGENT[/white]           [dim]pure / enhanced / trojan bind[/dim]

    [dim]0. Exit          keeper: tunnel+listener 24/7[/dim]
"""

menu2 = """
    [bold white]── CONNECTED DEVICES ────────────────────────────────────────[/bold white]

    [dim]1.[/dim] [white]LIST ALL DEVICES[/white]       [dim]USB + WiFi + saved[/dim]
    [dim]2.[/dim] [white]CONNECT TO DEVICE[/white]     [dim]pick device → connect[/dim]
    [dim]3.[/dim] [white]RECONNECT LAST[/white]        [dim]quick reconnect[/dim]
    [dim]4.[/dim] [white]DEVICE INFO[/white]           [dim]model, Android, IP, battery[/dim]
    [dim]5.[/dim] [white]PULL APKs[/white]             [dim]extract all installed apps[/dim]
    [dim]6.[/dim] [white]GRANT PERMISSIONS[/white]     [dim]silent grant all perms[/dim]

    [dim]99. Back to Main[/dim]
"""

menu3 = """
    [bold white]── BUILD AGENT ──────────────────────────────────────────────[/bold white]

    [dim]1.[/dim] [white]PURE BUILD[/white]            [dim]no msfvenom · stealthy[/dim]
    [dim]2.[/dim] [white]ENHANCED BUILD[/white]        [dim]msfvenom + 6-layer[/dim]
    [dim]3.[/dim] [white]TROJAN BIND[/white]           [dim]inject into legit APK[/dim]
    [dim]4.[/dim] [white]WORK PROFILE DEPLOY[/white]   [dim]hidden profile[/dim]
    [dim]5.[/dim] [white]DEPLOY TO DEVICE[/white]      [dim]install + perms + launch[/dim]

    [dim]99. Back to Main[/dim]
"""

menu4 = """
    [bold white]── C2 & TUNNEL ──────────────────────────────────────────────[/bold white]

    [dim]1.[/dim] [white]START KEEPER[/white]          [dim]24/7 listener + tunnel[/dim]
    [dim]2.[/dim] [white]CLOUDFLARE TUNNEL[/white]     [dim]international routing[/dim]
    [dim]3.[/dim] [white]PORTMAP TUNNEL[/white]        [dim]legacy portmap.io[/dim]
    [dim]4.[/dim] [white]KEEPER STATUS[/white]         [dim]sessions + connections[/dim]

    [dim]99. Back to Main[/dim]
"""

menu5 = """
    [bold white]── DATA ACCESS ──────────────────────────────────────────────[/bold white]

    [dim]1.[/dim] [white]SCREENSHOT[/white]            [dim]capture screen[/dim]
    [dim]2.[/dim] [white]SCREEN RECORD[/white]         [dim]record screen[/dim]
    [dim]3.[/dim] [white]SMS DUMP[/white]              [dim]read all SMS[/dim]
    [dim]4.[/dim] [white]CONTACTS DUMP[/white]         [dim]read all contacts[/dim]
    [dim]5.[/dim] [white]CALL LOGS[/white]             [dim]read call history[/dim]
    [dim]6.[/dim] [white]LOCATION[/white]              [dim]get GPS location[/dim]
    [dim]7.[/dim] [white]CAMERA[/white]                [dim]launch / live view[/dim]
    [dim]8.[/dim] [white]MICROPHONE[/white]            [dim]record audio[/dim]
    [dim]9.[/dim] [white]FILE BROWSER[/white]          [dim]browse /sdcard/[/dim]
    [dim]10.[/dim] [white]APP LIST[/white]             [dim]list installed apps[/dim]
    [dim]11.[/dim] [white]SYSTEM INFO[/white]          [dim]device info · battery[/dim]
    [dim]12.[/dim] [white]SEND SMS[/white]             [dim]send SMS from device[/dim]
    [dim]13.[/dim] [white]OPEN URL[/white]             [dim]open URL on device[/dim]

    [dim]99. Back to Main[/dim]
"""

menu6 = """
    [bold white]── SHELL ACCESS ─────────────────────────────────────────────[/bold white]

    [dim]1.[/dim] [white]INTERACTIVE SHELL[/white]     [dim]direct shell on device[/dim]
    [dim]2.[/dim] [white]KEEPER SHELL[/white]          [dim]shell via C2 tunnel[/dim]
    [dim]3.[/dim] [white]RUN COMMAND[/white]           [dim]one-shot command[/dim]
    [dim]4.[/dim] [white]MIRROR SCREEN[/white]         [dim]scrcpy live mirror[/dim]

    [dim]99. Back to Main[/dim]
"""

menu = [menu1, menu2, menu3, menu4, menu5, menu6]
