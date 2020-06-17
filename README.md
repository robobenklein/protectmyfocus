# Protect My Focus - Take it back forcefully!

This program helps defend your focus from being stolen by annoying applications like Steam or Discord restarting in the background while you're gaming or working on something else.

Since Gnome Shell hasn't actually fixed their window focus behaviour, we can't really prevent it before it happens, so if that doesn't work (like in Steam's case) we just move the focus back as soon as we can detect that it changed.

# Usage

Clone and run the `protectmyfocus.py` script with python 3.

Requires `wmctrl`, `xprop` to be available.

Tested on Pop!_OS 20.04
