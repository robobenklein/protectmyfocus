# Protect My Focus - Take it back forcefully!

This program helps defend your focus from being stolen by annoying applications like Steam or Discord restarting in the background while you're gaming or working on something else.

Since Gnome Shell hasn't actually fixed their window focus behaviour, we can't really prevent it before it happens, so if that doesn't work (like in Steam's case) we just move the focus back as soon as we can detect that it changed.

# Usage

Clone / download this repo.

Install requirements with pip: `pip3 install -r requirements.txt`

Run the `protectmyfocus.py` script with python 3.

Requires `wmctrl`, `xprop` to be available. (`sudo apt install x11-utils wmctrl`)

Tested on Pop!_OS 20.04

# Config

To find the class name of a window, just read the output of the program and copy the name before the `/` in a window ID.

### Whitelist

Windows matching the classes in this list will always be allowed to gain focus.

### Startup time

`[startuptime]` is a set of class names along with how long that application's window should be prevented from gaining focus after it's been created.

E.x. `Steam = 2.0` means that all Steam windows will not be allowed to steal focus for 2 seconds after they've been created.

# Caveats

Fullscreen games that misbehave when focus is lost may not play well with this program. It's recommended to run either in borderless mode or make sure that Alt-Tabbing in and out of the game works without issues before using this program.

# A better approach

If I were some kind of expert with X.Org X11 and could find each and every call to a window management function that Steam, Discord, etc. actually make, then I'd probably have written a C/C++ wrapper / library call interceptor.
