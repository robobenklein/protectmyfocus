# Protect My Focus - Take it back forcefully!

This program helps defend your focus from being stolen by annoying applications like Steam or Discord restarting in the background while you're gaming or working on something else.

Since Gnome Shell hasn't actually fixed their window focus behaviour, we can't really prevent it before it happens, so if that doesn't work (like in Steam's case) we just move the focus back as soon as we can detect that it changed.

# Usage

Clone and run the `protectmyfocus.py` script with python 3.

Requires `wmctrl`, `xprop` to be available.

Tested on Pop!_OS 20.04

# Caveats

Fullscreen games that misbehave when focus is lost may not play well with this program. It's recommended to run either in borderless mode or make sure that Alt-Tabbing in and out of the game works without issues before using this program.

# A better approach

If I were some kind of expert with X.Org X11 and could find each and every call to a window management function that Steam, Discord, etc. actually make, then I'd probably have written a C/C++ wrapper / library call interceptor.
