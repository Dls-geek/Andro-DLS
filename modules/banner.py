# Andro-DLS — Banner & Menu System
# Copyright (c) 2025–2026 Khurshid Jhon & Dls-geek Team

version = "v3.0.0"

# ─── Main Menu (Page 0) ───────────────────────────────────────────────────
menu1 = """
    [bold yellow]── ANDRO-DLS · PHONE CONTROL ───────────────────────────────────[/bold yellow]

    [white]1.[/white] [green]▸ USB SETUP[/green]              [dim]cable connect → tcpip 5555 → wireless[/dim]
    [white]2.[/white] [green]▸ CONNECTED DEVICES[/green]     [dim]see all · reconnect · manage[/dim]
    [white]3.[/white] [green]▸ BUILD AGENT[/green]           [dim]pure / enhanced / trojan bind[/dim]

    [dim]0. Exit          keeper: tunnel+listener 24/7 in background[/dim]
"""

# ─── Connected Devices (Page 1) ────────────────────────────────────────────
menu2 = """
    [bold cyan]── CONNECTED DEVICES ───────────────────────────────────────────[/bold cyan]

    [white]1.[/white] [green]▸ LIST ALL DEVICES[/green]       [dim]USB + WiFi + saved[/dim]
    [white]2.[/white] [green]▸ CONNECT TO DEVICE[/green]     [dim]pick device → connect[/dim]
    [white]3.[/white] [green]▸ RECONNECT LAST[/green]        [dim]quick reconnect to last device[/dim]
    [white]4.[/white] [green]▸ DEVICE INFO[/green]           [dim]model, Android ver, IP, battery[/dim]
    [white]5.[/white] [green]▸ PULL APKs[/green]             [dim]extract all installed apps[/dim]
    [white]6.[/white] [green]▸ GRANT PERMISSIONS[/green]     [dim]silent grant all runtime perms[/dim]

    [dim]99. Back to Main Menu[/dim]
"""

# ─── Build Agent (Page 2) ──────────────────────────────────────────────────
menu3 = """
    [bold magenta]── BUILD AGENT ───────────────────────────────────────────────[/bold magenta]

    [white]1.[/white] [green]▸ PURE BUILD[/green]            [dim]no msfvenom · most stealthy[/dim]
    [white]2.[/white] [green]▸ ENHANCED BUILD[/green]        [dim]msfvenom base + 6-layer injection[/dim]
    [white]3.[/white] [green]▸ TROJAN BIND[/green]           [dim]inject agent into legit APK[/dim]
    [white]4.[/white] [green]▸ WORK PROFILE DEPLOY[/green]   [dim]hidden profile · cross-resurrection[/dim]
    [white]5.[/white] [green]▸ DEPLOY TO DEVICE[/green]      [dim]install + grant perms + launch[/dim]

    [dim]99. Back to Main Menu[/dim]
"""

# ─── C2 & Tunnel (Page 3) ─────────────────────────────────────────────────
menu4 = """
    [bold red]── C2 & TUNNEL ─────────────────────────────────────────────────[/bold red]

    [white]1.[/white] [green]▸ START KEEPER[/green]          [dim]24/7 listener + tunnel[/dim]
    [white]2.[/white] [green]▸ CLOUDFLARE TUNNEL[/green]     [dim]international routing · no port fwd[/dim]
    [white]3.[/white] [green]▸ PORTMAP TUNNEL[/green]        [dim]legacy portmap.io tunnel[/dim]
    [white]4.[/white] [green]▸ KEEPER STATUS[/green]         [dim]check sessions + connections[/dim]

    [dim]99. Back to Main Menu[/dim]
"""

# ─── Data Access (Page 4) ──────────────────────────────────────────────────
menu5 = """
    [bold blue]── DATA ACCESS ─────────────────────────────────────────────────[/bold blue]

    [white]1.[/white] [green]▸ SCREENSHOT[/green]            [dim]capture screen[/dim]
    [white]2.[/white] [green] SCREEN RECORD[/green]         [dim]record screen[/dim]
    [white]3.[/white] [green]▸ SMS DUMP[/green]              [dim]read all SMS messages[/dim]
    [white]4.[/white] [green]▸ CONTACTS DUMP[/green]         [dim]read all contacts[/dim]
    [white]5.[/white] [green]▸ CALL LOGS[/green]             [dim]read call history[/dim]
    [white]6.[/white] [green]▸ LOCATION[/green]              [dim]get GPS location[/dim]
    [white]7.[/white] [green]▸ CAMERA[/green]                [dim]launch camera / live view[/dim]
    [white]8.[/white] [green]▸ MICROPHONE[/green]            [dim]record audio[/dim]
    [white]9.[/white] [green]▸ FILE BROWSER[/green]          [dim]browse /sdcard/ · pull files[/dim]
    [white]10.[/white] [green]▸ APP LIST[/green]             [dim]list all installed apps[/dim]
    [white]11.[/white] [green]▸ SYSTEM INFO[/green]          [dim]device info · battery · network[/dim]
    [white]12.[/white] [green]▸ SEND SMS[/green]             [dim]send SMS from device[/dim]
    [white]13.[/white] [green] OPEN URL[/green]             [dim]open URL on device[/dim]

    [dim]99. Back to Main Menu[/dim]
"""

# ─── Shell Access (Page 5) ─────────────────────────────────────────────────
menu6 = """
    [bold green]── SHELL ACCESS ────────────────────────────────────────────────[/bold green]

    [white]1.[/white] [green]▸ INTERACTIVE SHELL[/green]     [dim]direct shell on device[/dim]
    [white]2.[/white] [green]▸ KEEPER SHELL[/green]          [dim]shell via C2 tunnel[/dim]
    [white]3.[/white] [green]▸ RUN COMMAND[/green]           [dim]one-shot command[/dim]
    [white]4.[/white] [green]▸ MIRROR SCREEN[/green]         [dim]scrcpy live mirror + control[/dim]

    [dim]99. Back to Main Menu[/dim]
"""

menu = [menu1, menu2, menu3, menu4, menu5, menu6]

# ─── Banners (ALL say ANDRO-DLS — zero PhoneSploit) ────────────────────────

banner1 = """
     █████╗ ███╗   ██╗ ██████╗ ███╗   ██╗ ██████╗ ███████╗
    ██╔══██╗████╗  ██║██╔════╝ ████╗  ██║██╔═══██╗██╔════╝
    ███████║██╔██╗ ██║██║  ███╗██╔██╗ ██║██║   ██║█████╗
    ██╔══██║██║██╗██║██║   ██║██║╚██╗██║██║   ██║██╔══╝
    ██║  ██║██║ ╚████║██████╔╝██║ ╚████║╚██████╔╝███████╗
    ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ ╚══════╝


            [red]{version}[/red]                [white]By Khurshid Jhon & Dls-geek Team[/white]
""".format(version=version)

banner2 = """
        ███╗   ███╗ ██████╗  ██████╗ ███████╗ █████╗ ██╗   ██╗██╗      █████╗ ████████╗ ██████╗ ██████╗
        ████╗ ████║██═══██╗██╔════╝ ██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗╚══██╔══╝██╔═══██╗██══██╗
        ██╔██████║██║   ██║██║  ███╗█████╗  ███████║██║   ██║██║     ███████║   ██║   ██║   ██║██████╔╝
        ██║╚██╔╝██║██║   ██║██║   ██║██╔══╝  ██══██║██║   ██║██║     ██╔══██║   ██║   ██║   ██║██╔══██╗
        ██║ ╚═╝ ██║██████╔╝╚██████╗ ███████╗██║  ██║╚██████╔╝███████╗██║  ██║   ██║   ╚██████╔╝██║  ██║
        ╚═╝     ╚═╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝


            [red]{version}[/red]            [white]By Khurshid Jhon & Dls-geek Team[/white]
""".format(version=version)

banner3 = """
    ██████╗ ███████╗ ██████╗ ██╗███████╗██╗   ██╗██████╗ ███████╗
    ██╔══██╗██╔════╝██╔═══██╗██║██╔════╝██║   ██║██╔══██╗██╔════╝
    ██║  ██║█████╗  ██║   ██║██║███████╗██║   ██║██████╔╝█████╗
    ██║  ██║██╔══╝  ██║   ██║██║╚════██║██║   ██║██╔══██╗██╔══╝
    ██████╔╝███████╗██████╔╝██║███████║╚██████╔╝██║  ██║███████╗
    ╚═════╝ ╚══════╝ ╚═════╝ ╚═╝╚══════╝ ═════╝ ╚═╝  ╚═╝╚══════╝


            [red]{version}[/red]                [white]By Khurshid Jhon & Dls-geek Team[/white]
""".format(version=version)

banner4 = """
        ░█▀█ █──█ █▀▀█ █▀▀▄ █▀ ░█▀▀▀█ █▀█ █── █▀█ ─▀─ ▀▀█▀▀  ░█▀█ █▀▀█ █▀█
        ░█▄▄█ █▀▀█ █──█ █──█ █▀▀ ─▀▀▀▄▄ █──█ █── █──█ ▀█▀ ──█──  ░█▄▄█ █▄▀ █──█
        ░█─── ▀──▀ ▀▀▀▀ ▀──▀ ▀▀ ░█▄▄▄█ █▀▀ ▀▀ ▀▀▀▀ ▀▀ ──▀──  ░█─── ▀─▀▀ ▀▀▀▀


            [red]{version}[/red]            [white]By Khurshid Jhon & Dls-geek Team[/white]
""".format(version=version)

banner5 = """
        █▀█ █░█ █▀█ █▄░█ █▀▀ █▀ █▀█ █░░ █▀█ █ ▀█   █▀█ █▀█ ██
        █▀▀ █▀█ █▄█ █░▀█ ██ ▄█ █▀▀ █▄▄ █▄█ █ ░█░   █▀▀ █▀▄ ██


            [red]{version}[/red]             [white]By Khurshid Jhon & Dls-geek Team[/white]
""".format(version=version)

banner6 = """
       ___  __                 ____     __     _ __     ___
      / _ \\/ /  ___  ___  ___ / __/__  / /__  (_) /_   / _ \\_______
     / ___/ _ \\/ _ \\/ _ \\/ -_)\\ \\/ _ \\/ / _ \\/ / __/  / ___/ __/ _ \\
    /_/  /_//_/\\___/_//_/\\__/___/ .__/_/\\___/_/\\__/  /_/  /_/  \\___/
                               /_/

        [red]{version}[/red]        [white]By Khurshid Jhon & Dls-geek Team[/white]
""".format(version=version)

banner_list = [banner1, banner2, banner3, banner4, banner5, banner6]

# ─── Instructions ──────────────────────────────────────────────────────────

instructions_banner = """[cyan]
        ╔══════════════════════════════════════════════════════════╗
        ║              ANDRO-DLS · QUICK GUIDE                    ║
        ╠══════════════════════════════════════════════════════════╣
        ║  Step 1: USB SETUP (Option 1)                          ║
        ║    → Connect phone via USB cable                       ║
        ║    → Enable USB debugging on phone                     ║
        ║    → Tool switches phone to wireless ADB               ║
        ║    → Remove cable — everything works over WiFi now     
        ║                                                        ║
        ║  Step 2: CONNECTED DEVICES (Option 2)                  ║
        ║    → See all connected devices                         ║
        ║    → Pick device → connect                             ║
            → Pull APKs, grant permissions, manage              ║
        ║                                                        ║
        ║  Step 3: BUILD AGENT (Option 3)                        ║
        ║    → Pure / Enhanced / Trojan Bind                     ║
        ║    → Deploy to device → agent runs hidden              ║
        ║                                                        ║
        ║  Step 4: C2 & TUNNEL (after deploy)                    ║
            → Start keeper → Cloudflare tunnel                  ║
        ║    → Agent connects → full control from anywhere       ║
        ║                                                        
        ║  Step 5: DATA ACCESS                                   ║
        ║    → Screenshots, SMS, contacts, camera, mic, location ║
        ║    → All over C2 tunnel — any network, any country     ║
        ╚══════════════════════════════════════════════════════════╝
[/cyan]"""
