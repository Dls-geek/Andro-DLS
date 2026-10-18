"""
    COPYRIGHT DISCLAIMER

    Script : Andro-DLS - All in One Android Hacking ADB Toolkit

    Copyright (C) 2026  Khurshid Jhon (github.com/Dls-geek)

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
"""

from modules import console
from control_room.cli import run

_orig_adb = console.adb


def _adb(args, *rest, **kwargs):
    if isinstance(args, str):
        args = args.split()
    return _orig_adb(args, *rest, **kwargs)


console.adb = _adb

if __name__ == "__main__":
    run()
