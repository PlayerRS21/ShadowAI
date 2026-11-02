import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional


MAX_OUTPUT = 2000
GRACE_SECONDS = 3.0
MARK = "__SHADOW_CWD__"    # hidden marker used to learn the shell's final folder

_cwd = os.getcwd()         # remembered folder, so `cd` carries over between steps

# Last-resort safety net (the model can be wrong, this check can't be talked out of it)
BLOCKED = (
    "rm -rf /", "rm -rf ~", "rm -rf *", "mkfs", "dd if=", ":(){",
    "diskpart", "format c:", "format-volume", "clear-disk", "rd /s /q c:\\",
)

# Linux terminal emulators and the flags each needs to run "bash -c <script>"
LINUX_TERMINALS = [
    ("x-terminal-emulator", ["-e", "bash", "-c"]),
    ("gnome-terminal",      ["--", "bash", "-c"]),
    ("konsole",             ["-e", "bash", "-c"]),
    ("xfce4-terminal",      ["-e", "bash -c"]),   # takes one string, handled below
    ("kitty",               ["bash", "-c"]),
    ("alacritty",           ["-e", "bash", "-c"]),
    ("wezterm",             ["start", "--", "bash", "-c"]),
    ("ghostty",             ["-e", "bash", "-c"]),
    ("foot",                ["bash", "-c"]),
    ("xterm",               ["-e", "bash", "-c"]),
]

# Matches a trailing "&" (with optional "> /dev/null 2>&1" before it)
_BG_SUFFIX = re.compile(r"\s*(?:>\s*/dev/null)?\s*(?:2>&1)?\s*&\s*$")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def os_family() -> str:
    """Return 'Windows', 'macOS' or 'Linux'. Never returns None."""
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("linux"):
        return "Linux"
    return sys.platform


def has_display() -> bool:
    """True if a GUI session exists (needed to open a terminal window)."""
    if os_family() == "Linux":
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def _trim(text: str) -> str:
    """Cut long output so the model's request never gets too big."""
    text = (text or "").replace("\x00", "").strip()
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + "\n...[output truncated]"
    return text


def _result(os_name: str, **fields) -> Dict[str, Any]:
    return {"os": os_name, **fields}


def _shell_quote(text: str) -> str:
    """Wrap text in single quotes for a POSIX shell."""
    return "'" + text.replace("'", "'\\''") + "'"


def _shell_args(command: str, os_name: str, track_cwd: bool) -> list:
    """Build the argument list that runs `command` in the right shell for this OS.
    track_cwd=True appends a hidden marker so we learn the final folder (for `cd`)."""
    if os_name == "Windows":
        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command
        if track_cwd:
            # Print the folder on its own line, then exit with the command's real result
            script += ('\n$__ok=$?; $__rc=$LASTEXITCODE; '
                       'Write-Output "`n' + MARK + '$((Get-Location).Path)"; '
                       'if($__ok){exit 0}elseif($__rc){exit $__rc}else{exit 1}')
        return [exe, "-NoProfile", "-Command", script]

    shell = shutil.which("bash") or shutil.which("sh") or "/bin/sh"  # Alpine has only sh
    script = command
    if track_cwd:
        # Remember the exit code, print the folder, then exit with the ORIGINAL code
        script += f'\n__rc=$?\nprintf \'\\n{MARK}%s\\n\' "$PWD"\nexit $__rc'
    return [shell, "-c", script]


def _extract_cwd(stdout: str) -> str:
    """Remove our hidden marker line from the output and update the remembered folder."""
    global _cwd
    kept = []
    for line in stdout.splitlines():
        if line.startswith(MARK):
            new_dir = line[len(MARK):].strip()
            if os.path.isdir(new_dir):
                _cwd = new_dir
        else:
            kept.append(line)
    return "\n".join(kept)


def _auto_background(command: str, os_name: str) -> Optional[str]:
    """If a POSIX command ends with '&' (e.g. 'nohup mpv x >/dev/null 2>&1 &'), return it
    cleaned up so we can run it in background mode instead. Otherwise return None."""
    if os_name == "Windows":
        return None
    c = command.strip()
    if not c.endswith("&") or c.endswith("&&"):
        return None
    c = _BG_SUFFIX.sub("", c)                 # drop the redirects and trailing &
    c = re.sub(r"^\s*nohup\s+", "", c)        # drop a leading nohup
    return c or None


# ---------------------------------------------------------------------------
# Interactive mode: opens a visible terminal window
# ---------------------------------------------------------------------------
def _run_interactive(command: str, os_name: str) -> Dict[str, Any]:
    try:
        if os_name == "Linux":
            term = next(((t, a) for t, a in LINUX_TERMINALS if shutil.which(t)), None)
            if term is None:
                return _result(os_name, success=False, type="non-static",
                               error="No supported terminal emulator found.")
            script = f"{command}; echo; echo '--- Process Exited ---'; read -p 'Press Enter to exit...'"
            name, flags = term
            if name == "xfce4-terminal":      # wants the whole command as ONE string
                process = subprocess.Popen([name, "-e", f"bash -c {_shell_quote(script)}"])
            else:
                process = subprocess.Popen([name, *flags, script])

        elif os_name == "macOS":
            safe = command.replace("\\", "\\\\").replace('"', '\\"')
            process = subprocess.Popen(
                ["osascript", "-e", f'tell app "Terminal" to do script "{safe}"'])

        elif os_name == "Windows":
            exe = shutil.which("pwsh") or "powershell"
            process = subprocess.Popen([exe, "-NoExit", "-Command", command],
                                       creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            return _result(os_name, success=False, type="non-static",
                           error=f"Unsupported OS: {os_name}")

        return _result(os_name, success=True, type="non-static",
                       status=f"Opened a terminal for: {command}", pid=process.pid)
    except Exception as e:
        return _result(os_name, success=False, type="non-static", error=str(e))


# ---------------------------------------------------------------------------
# Headless mode: run, wait, capture output
# ---------------------------------------------------------------------------
def _run_headless(command: str, timeout: int, os_name: str) -> Dict[str, Any]:
    try:
        proc = subprocess.Popen(
            _shell_args(command, os_name, track_cwd=True),
            cwd=_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,          # password prompts fail fast instead of hanging
            text=True,
            encoding="utf-8",
            errors="replace",                  # bad bytes become '?', never a crash
            start_new_session=(os_name != "Windows"),   # own process group, killable as one
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Kill the shell AND everything it started
            if os_name == "Windows":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return _result(os_name, success=False, type="static", exit_code=-1, stdout="",
                           stderr=f"Timed out after {timeout} seconds and was stopped.")

        stdout = _extract_cwd(stdout)
        return _result(os_name, success=proc.returncode == 0, type="static",
                       exit_code=proc.returncode, stdout=_trim(stdout),
                       stderr=_trim(stderr), cwd=_cwd)
    except Exception as e:
        return _result(os_name, success=False, type="static", exit_code=-1,
                       stdout="", stderr=str(e))


# ---------------------------------------------------------------------------
# Background mode: launch detached, then CHECK whether it is really running
# ---------------------------------------------------------------------------
def _run_background(command: str, os_name: str, grace: float) -> Dict[str, Any]:
    # Output goes to a temp log file so we can read early errors without blocking
    log_path = os.path.join(tempfile.gettempdir(),
                            f"shadow_bg_{os.getpid()}_{int(time.time() * 1000)}.log")
    try:
        if os_name == "Windows":
            # No console window, and its own process group so it outlives this script
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            flags = {"start_new_session": True}      # detached from our terminal

        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                _shell_args(command, os_name, track_cwd=False),
                cwd=_cwd,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,            # errors land in the same log
                **flags,
            )

        # Watch it for a few seconds: did it survive startup?
        deadline = time.time() + grace
        while time.time() < deadline and proc.poll() is None:
            time.sleep(0.1)
        code = proc.poll()                           # None = still running

        # Read the last part of whatever it printed (warnings, errors, track title...)
        try:
            with open(log_path, "rb") as f:
                text = f.read().decode("utf-8", "replace").replace("\r", "\n")
        except OSError:
            text = ""
        tail = _trim(text[-800:])

        try:
            os.remove(log_path)       # fine on Linux/macOS; on Windows it may stay, so ignore errors
        except OSError:
            pass

        if code is None:
            return _result(os_name, success=True, type="background", running=True,
                           pid=proc.pid, output=tail)
        return _result(os_name, success=(code == 0), type="background", running=False,
                       pid=proc.pid, exit_code=code, output=tail)
    except Exception as e:
        return _result(os_name, success=False, type="background", running=False,
                       exit_code=-1, output=str(e))


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------
def executeCommand(command: str, is_interactive: bool = False, timeout: int = 30,
                   background: bool = False) -> Dict[str, Any]:
    """Run a command on Windows, macOS or Linux and return a dict describing the result.
    background=True is for long-running programs (players, apps, servers)."""
    os_name = os_family()

    if not isinstance(command, str) or not command.strip():
        return _result(os_name, success=False, type="static", exit_code=-1,stdout="", stderr="Empty command.")
    if any(bad in command.lower() for bad in BLOCKED):
        return _result(os_name, success=False, type="static", exit_code=-1,stdout="", stderr="Blocked by safety filter.")

    # Safety net: if the model still sends 'nohup ... &', treat it as a background launch
    if not background:
        cleaned = _auto_background(command, os_name)
        if cleaned:
            command, background = cleaned, True

    if background:
        return _run_background(command, os_name, GRACE_SECONDS)
    if is_interactive and has_display():
        return _run_interactive(command, os_name)
    return _run_headless(command, timeout, os_name)


def format_result(r: Dict[str, Any]) -> str:
    """Turn the result dict into the 'RESULT:' text sent back to the model."""
    kind = r.get("type")
    if kind == "non-static":
        return r.get("status") or f"error: {r.get('error')}"
    if kind == "background":
        if r.get("running"):
            state = f"STARTED and still running after {GRACE_SECONDS:g}s (pid {r.get('pid')})"
        else:
            state = (f"EXITED with code {r.get('exit_code')} within {GRACE_SECONDS:g}s "
                     "(a launcher may have handed off to another process if the code is 0)")
        return state + (f"\n{r['output']}" if r.get("output") else "")
    out = r.get("stdout") or r.get("stderr") or "(no output)"
    if r.get("stdout") and r.get("stderr"):
        out += f"\n[stderr] {r['stderr']}"
    return f"exit={r['exit_code']}\n{out}"


# ---------------------------------------------------------------------------
# Self-test: run `python commandEngine.py` (works on Linux, macOS and Windows)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # PowerShell needs '&' to run a quoted path
    py = ("& " if os_family() == "Windows" else "") + f'"{sys.executable}"'
    tests = [
        ("echo hello",                                         {}),                # prints hello
        ("exit 3",                                             {}),                # exit=3
        (f'cd "{tempfile.gettempdir()}"',                      {}),                # change folder
        ("pwd",                                                {}),                # shows temp folder
        (f'{py} -c "import time; time.sleep(5)"',             {"timeout": 2}),    # times out
        (f'{py} -c "import time; time.sleep(30)"',            {"background": True}),  # STARTED, running
        (f'{py} -c "import sys; sys.exit(4)"',                {"background": True}),  # EXITED with code 4
    ]
    for cmd, opts in tests:
        print(f"{cmd!r} {opts}\n  -> {format_result(executeCommand(cmd, **opts))}\n")
