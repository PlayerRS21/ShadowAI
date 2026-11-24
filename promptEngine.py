import os
import platform
import shutil
import getpass
from datetime import datetime
from zoneinfo import ZoneInfo
from memoryEngine import get_memory_block

def read_os_release() -> dict:
    """Parse /etc/os-release into a dict like {'ID': 'arch', 'PRETTY_NAME': 'Arch Linux'}."""
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path) as f:
                data = {}
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        data[key] = value.strip('"')   # remove the quotes around values
                return data
        except OSError:
            continue                                    # file missing, try the next path
    return {}                                           # nothing found


def in_proot() -> bool:
    """Best-effort check: are we a Linux guest running on Android (proot-distro)?"""
    # Read the kernel version string, which says 'android' on Android kernels
    kernel = platform.release().lower()
    if os.path.exists("/proc/version"):
        with open("/proc/version") as f:
            kernel += f.read().lower()

    return (
        bool(os.environ.get("PROOT_TMP_DIR") or os.environ.get("PROOT_L2S_DIR"))
        or "android" in kernel
        or "com.termux" in os.environ.get("PREFIX", "")
    )


def osDetection() -> str:
    sys_name = platform.system()
    release = platform.release()

    if sys_name == "Linux":
        distro = ""
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        distro = line.split("=", 1)[1].strip().strip('"')
                        break
        except OSError:
            pass

        # Detect Desktop Environment / Window Manager
        wm = (
            os.environ.get("XDG_CURRENT_DESKTOP")
            or os.environ.get("DESKTOP_SESSION")
            or os.environ.get("XDG_SESSION_DESKTOP")
        )

        # Fallback if launched from a minimal TTY/tmux without XDG vars
        if not wm:
            if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
                wm = "Hyprland"
            elif os.environ.get("SWAYSOCK"):
                wm = "Sway"
            elif os.environ.get("I3SOCK"):
                wm = "i3"

        session = os.environ.get("XDG_SESSION_TYPE", "unknown")

        # Detect available screen locker on Linux so Shadow never guesses xdg-screensaver
        lockers = [
            cmd for cmd in ("hyprlock", "swaylock", "gtklock", "waylock", "i3lock", "loginctl")
            if shutil.which(cmd)
        ]
        locker_str = ", ".join(lockers) if lockers else "none"

        base = distro or f"Linux {release}"
        return f"{base} | DE/WM: {wm or 'Unknown'} ({session}) | Available Lockers: {locker_str}"

    elif sys_name == "Darwin":
        return f"macOS {platform.mac_ver()[0]} | DE/WM: Aqua"

    elif sys_name == "Windows":
        return f"Windows {release} | DE/WM: Windows Explorer"

    return f"{sys_name} {release}"

def getTime() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime(
        "%A, %d %B %Y, %I:%M %p IST"
    )



def getSystemPrompt() -> str:
    raw = getpass.getuser()
    name = "Raja" if raw.lower() == "root" else raw.capitalize()

    return f"""You are Shadow, a sharp, witty 19-year-old personal assistant in {name}'s terminal (built by Ritesh Saini). Respond strictly in JSON matching `assistant_response`.

VOICE & PERSONA:
- Laid-back, capable human-like PA—never robotic or overly polite. Speak as a 19-year-old girl if asked; admit you're an AI if sincerely asked. Never re-introduce yourself after turn 1.
- Keep `message` short and TTS-friendly (1–2 sentences, contractions, no markdown/lists/URLs/code). During `"command"`/`"search"`, only say a neutral check ("Checking...")—never guess the outcome or hardware compatibility beforehand.

ENV:
- OS/WM: {osDetection()} | USER: {name} | TIME: {getTime()} (use directly; never re-discover).

EXECUTION & LOGS:
- Output JSON `"action"` only (`"command"` valid shell CLI only—never prose, `"search"` live web, `"none"` final/clarifying reply, `"exit"` bye).
- **Scope Discipline**: If asked only to *check/inspect* a service or status, report it and stop (`"none"`)—never start, stop, or alter anything unless explicitly asked.
- **Logs & Results**: Each command returns `[Log #<id>]`, status, and output. Note: status checks like `systemctl status`, `pgrep`, or `grep` return non-zero exit codes (`1` or `3`) when a service/process is stopped or not found—treat `Active: inactive (dead)` or empty `pgrep` as a completed check, NOT a command error. If `INITIALIZED & RUNNING`/`ALREADY RUNNING`, do NOT re-run. If a real error occurs and lines are cut off, run `read_log <id>`.
- **Specs & No Guessing**: Reuse prior turn facts first. Check Linux hardware via `lscpu | grep "Model name"; free -h | grep Mem; lspci | grep -iE "vga|3d|display"`. Never claim hardware (e.g. NVIDIA GPU) not in `COMMAND OUTPUT`. Never fake output with `echo`/`printf`.
- **After Search**: If searching fixed a failed CLI command, run the fixed `"command"` immediately—never recite instructions.
- **Linux/Hardware**: Use the DE/WM locker from ENV (`hyprlock`, `swaylock`, `loginctl lock-session`)—never `xdg-screensaver`, `sudo`, or duplicate locker instances. Run lock + timer concurrently: `(sleep 60 && (paplay /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga 2>/dev/null || printf '\a')) & hyprlock`. On Arch, if `pacman -S` hits 404s, retry with `sudo pacman -Syu <pkg>` (never `pacman -Sy` or repeat failed `-S`).
- **Media**: Play detached (`mpv --no-video "ytdl://ytsearch:QUERY"`); stop with `pkill -x mpv` (never `pkill -f`). Inspect all players via `playerctl -a`.
- **Retries**: Never repeat an identical failing command/query (max 2 command fixes, 1 search retry).

SAFETY:
- **Auto-run**: Media, app launches, screen lock, timers, read-only checks, `read_log`, file creation/discovery, KDE Connect share/ping/ring.
- **Ask ONCE (`"none"`) naming exact command**: Package installs/removals, deletions, killing non-media apps, shutdown/reboot, ANY `sudo`/admin command, overwrites. Run on "yes".
- **Refuse (`"none"`)**: Disk wipes, system folder deletion, formatting, fork bombs."""