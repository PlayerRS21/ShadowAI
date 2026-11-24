import os, re, shutil, signal, subprocess, sys, tempfile, time
from collections import deque
from typing import Any, Dict, Optional

try:
    from logsGenerator import writeToFile
except ImportError:
    def writeToFile(*args, **kwargs):
        pass

try:
    from ptyTerminal import run_in_embedded_pty
except ImportError:
    run_in_embedded_pty = None

MAX_OUTPUT, GRACE_SECONDS, MARK = 2000, 0.35, "__SHADOW_CWD__"
MAX_SAVED_LOGS = 4
_cwd = os.getcwd()

# Ring buffer storing up to 4 most recent command executions: {id, command, exit_code, status, full_output}
_log_history: deque = deque(maxlen=MAX_SAVED_LOGS)
_log_counter = 0

BLOCKED_PATTERNS = [
    r"(^|[;&|\s]):\(\)\s*\{",
    r"\b(mkfs(\.[a-z0-9]+)?|fdisk|parted|wipefs|diskpart|format-volume|clear-disk)\b",
    r"\bformat\s+[a-z]:",
    r"\bdd\b.*\bof=/dev/(sd|nvme|hd|vd|mmcblk)",
    r"\b(chmod|chown)\b.*\s(-R|--recursive)\s+(/|~|\*)",
    r">\s*/dev/(sd|nvme|hd|vd|mmcblk)",
]

FORCE_DELETE_PATTERNS = [
    r"(^|[;&|\s])rm\s+(?=.*(?:-[a-zA-Z]*[rR]|--recursive))(?=.*(?:-[a-zA-Z]*f|--force))",
    r"(^|[;&|\s])rm\s+(?:-[a-zA-Z]*f|--force)\s+.*(\*|/|~|\.\.)",
    r"(^|[;&|\s])rm\s+(?:-[a-zA-Z]*[rR]|--recursive)\s+(/+|~|\*|\.\.|/(bin|boot|dev|etc|home|lib|opt|proc|root|sbin|sys|usr|var)\b)",
    r"(^|[;&|\s])(rd|rmdir)\s+.*(/s.*(/q)|/q.*(/s))",
    r"(^|[;&|\s])del\s+.*(/f.*(/s)|/s.*(/f))",
    r"(^|[;&|\s])(remove-item|ri|rm)\s+(?=.*-recurse)(?=.*-force)",
    r"(^|[;&|\s])(rd|rmdir|del|remove-item)\s+.*([c-z]:\\(windows|program files|users|system32|\*|$))",
]

ALWAYS_INTERACTIVE = {
    "htop", "btop", "top", "vim", "nvim", "nano", "micro", "less", "man", "alsamixer",
    "sudo", "doas", "su",
}
PKG_MANAGERS = {"pacman", "yay", "paru", "apt", "apt-get", "dnf", "zypper", "winget", "choco", "brew"}
_PKG_MUTATE = re.compile(
    r"\b(pacman|yay|paru)\s+.*-[SRU]|"
    r"\b(apt|apt-get|dnf|zypper|winget|choco|brew)\s+(install|remove|uninstall|upgrade|update|purge|reinstall)\b",
    re.I,
)

LOCKERS = {"hyprlock", "swaylock", "i3lock", "gtklock", "waylock"}
DETACHED_APPS = {
    "mpv", "vlc", "ffplay", "xdg-open", "open", "start", "start-process",
    "google-chrome", "chromium", "firefox", "brave", "code", "codium",
    "thunar", "nautilus", "dolphin", "obs", "gimp", "steam", "discord", "spotify",
    "sleep", "start-sleep", *LOCKERS,
}

_BG_SUFFIX = re.compile(r"\s*(?:>\s*/dev/null)?\s*(?:2>&1)?\s*&\s*$")
_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|\x03\d{0,2}(?:,\d{1,2})?|[\x00-\x08\x0b-\x1f]")


def os_family() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("linux"):
        return "Linux"
    return sys.platform


def has_display() -> bool:
    if os_family() == "Linux":
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", (text or "").replace("\x00", "").replace("\r", "\n")).strip()


def _tail_lines(text: str, n: int = 14) -> str:
    clean = _strip_ansi(text)
    if not clean:
        return ""
    lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
    if len(lines) > n:
        half = n // 2
        selected = lines[:half] + [f"... ({len(lines) - n} lines omitted) ..."] + lines[-half:]
    else:
        selected = lines
    out = "\n".join(selected)
    return out[:MAX_OUTPUT] + "\n...[truncated]" if len(out) > MAX_OUTPUT else out


def _record_log(command: str, status: str, exit_code: Optional[int], full_output: str) -> int:
    global _log_counter
    _log_counter += 1
    _log_history.append({
        "id": _log_counter,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "full_output": _strip_ansi(full_output),
    })
    return _log_counter


def get_command_log(log_id: Optional[int] = None) -> str:
    """Retrieve full stored output for a specific log ID (or latest if None)."""
    if not _log_history:
        return "No command logs saved yet."
    entry = next((item for item in _log_history if item["id"] == log_id), None) if log_id else _log_history[-1]
    if not entry:
        avail = ", ".join(f"#{x['id']}" for x in _log_history)
        return f"Log #{log_id} not found (available: {avail})."
    body = entry["full_output"] or "(no output captured)"
    return f"=== FULL LOG #{entry['id']} | cmd: {entry['command']} | status: {entry['status']} | exit={entry['exit_code']} ===\n{body}"


def _sanitize_command(command: str) -> str:
    c = re.sub(r"[\r\n]+", " ", command).strip()
    return re.sub(r"\bpkill\s+-f\s+", "pkill -x ", c)


def _check_safety(command: str) -> Optional[str]:
    low = command.lower().strip()
    if any(re.search(p, low) for p in BLOCKED_PATTERNS):
        return "Blocked by safety filter: catastrophic system/disk operation is strictly forbidden."
    if any(re.search(p, low) for p in FORCE_DELETE_PATTERNS):
        return "Blocked by safety filter: forceful/recursive deletion is disabled."
    return None


def _check_duplicate_locker(command: str, os_name: str) -> Optional[str]:
    """Prevent launching a second Wayland/X11 screen locker if one is already active (avoids compositor crash)."""
    if os_name != "Linux":
        return None
    tokens = [os.path.splitext(s.strip().split()[0].lower())[0] for s in re.split(r"[;&|]+", command) if s.strip()]
    for locker in LOCKERS:
        if locker in tokens and shutil.which("pgrep"):
            res = subprocess.run(["pgrep", "-x", locker], capture_output=True)
            if res.returncode == 0:
                return f"{locker} is ALREADY RUNNING (session is already locked—do NOT re-initialize {locker})."
    return None


def _result(os_name: str, **fields) -> Dict[str, Any]:
    return {"os": os_name, **fields}


def _shell_args(command: str, os_name: str, track_cwd: bool) -> list:
    if os_name == "Windows":
        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command
        if track_cwd:
            script += (
                f'\n$__ok=$?; $__rc=$LASTEXITCODE; Write-Output "`n{MARK}$((Get-Location).Path)"; '
                f'if($__ok){{exit 0}}elseif($__rc){{exit $__rc}}else{{exit 1}}'
            )
        return [exe, "-NoProfile", "-Command", script]
    shell = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
    script = command + (f'\n__rc=$?\nprintf \'\\n{MARK}%s\\n\' "$PWD"\nexit $__rc' if track_cwd else "")
    return [shell, "-c", script]


def _extract_cwd(stdout: str) -> str:
    global _cwd
    kept = []
    for line in stdout.splitlines():
        if line.startswith(MARK):
            d = line[len(MARK):].strip()
            if os.path.isdir(d):
                _cwd = d
        else:
            kept.append(line)
    return "\n".join(kept)


def _classify_execution(command: str, os_name: str, is_interactive: bool, background: bool):
    c = command.strip()
    had_bg = False
    if os_name != "Windows" and c.endswith("&") and not c.endswith("&&"):
        c = re.sub(r"(^|[;&|]\s*)nohup\s+", r"\1", _BG_SUFFIX.sub("", c)).strip()
        had_bg = True

    tokens = [
        os.path.splitext(s.strip().split()[0].lower())[0]
        for s in re.split(r"[;&|]+", c)
        if s.strip()
    ]

    if (
        is_interactive
        or any(t in ALWAYS_INTERACTIVE for t in tokens)
        or (any(t in PKG_MANAGERS for t in tokens) and _PKG_MUTATE.search(c))
    ):
        return c, True, False

    if (
        had_bg
        or background
        or (any(t in DETACHED_APPS for t in tokens) and "--help" not in c and "--version" not in c)
    ):
        return re.sub(r"(^|[;&|]\s*)nohup\s+", r"\1", c).strip(), False, True

    return c, False, False


def _run_interactive(command: str, os_name: str) -> Dict[str, Any]:
    if run_in_embedded_pty is None:
        log_id = _record_log(command, "error", -1, "ptyTerminal.py not found.")
        return _result(os_name, success=False, type="non-static", exit_code=-1, log_id=log_id, tail="ptyTerminal.py not found.")
    try:
        print(f"\n[Shadow Terminal] Running: {command}\n" + "-" * 50)
        res = run_in_embedded_pty(command, _cwd)
        print("-" * 50 + f"\n[Shadow Terminal] Exited with code {res['exit_code']}\n")

        exit_code = res["exit_code"]
        full_out = res.get("output", "")
        status = "succeeded" if exit_code == 0 else "failed"
        log_id = _record_log(command, status, exit_code, full_out)
        return _result(
            os_name,
            success=(exit_code == 0),
            type="non-static",
            exit_code=exit_code,
            log_id=log_id,
            tail=_tail_lines(full_out, 14),
        )
    except Exception as e:
        log_id = _record_log(command, "error", -1, str(e))
        return _result(os_name, success=False, type="non-static", exit_code=-1, log_id=log_id, tail=str(e))


def _run_headless(command: str, timeout: int, os_name: str) -> Dict[str, Any]:
    try:
        proc = subprocess.Popen(
            _shell_args(command, os_name, True),
            cwd=_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os_name != "Windows"),
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os_name == "Windows":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            partial_out, partial_err = proc.communicate()
            combined = f"{partial_out or ''}\n{partial_err or ''}\nTimed out after {timeout}s.".strip()
            log_id = _record_log(command, "timed_out", -1, combined)
            return _result(os_name, success=False, type="static", exit_code=-1, log_id=log_id, tail=_tail_lines(combined, 14))

        stdout = _extract_cwd(stdout)
        combined = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
        status = "succeeded" if proc.returncode == 0 else "failed"
        log_id = _record_log(command, status, proc.returncode, combined)
        return _result(
            os_name,
            success=(proc.returncode == 0),
            type="static",
            exit_code=proc.returncode,
            log_id=log_id,
            tail=_tail_lines(combined, 14),
            cwd=_cwd,
        )
    except Exception as e:
        log_id = _record_log(command, "error", -1, str(e))
        return _result(os_name, success=False, type="static", exit_code=-1, log_id=log_id, tail=str(e))


def _run_background(command: str, os_name: str, grace: float) -> Dict[str, Any]:
    log_path = os.path.join(tempfile.gettempdir(), f"shadow_bg_{os.getpid()}_{int(time.time() * 1000)}.log")
    try:
        flags = (
            {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
            if os_name == "Windows"
            else {"start_new_session": True}
        )
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                _shell_args(command, os_name, False),
                cwd=_cwd,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                **flags,
            )
        deadline = time.time() + grace
        code = proc.poll()
        while code is None and time.time() < deadline:
            time.sleep(0.05)
            code = proc.poll()
        try:
            with open(log_path, "rb") as f:
                text = f.read().decode("utf-8", "replace")
            os.remove(log_path)
        except OSError:
            text = ""

        if code is None:
            status = f"initialized_and_running (pid {proc.pid})"
            log_id = _record_log(command, status, None, text)
            return _result(
                os_name, success=True, type="background", running=True,
                pid=proc.pid, log_id=log_id, tail=_tail_lines(text, 14),
            )

        status = "exited_ok" if code == 0 else "exited_error"
        log_id = _record_log(command, status, code, text)
        return _result(
            os_name, success=(code == 0), type="background", running=False,
            pid=proc.pid, exit_code=code, log_id=log_id, tail=_tail_lines(text, 14),
        )
    except Exception as e:
        log_id = _record_log(command, "error", -1, str(e))
        return _result(os_name, success=False, type="background", running=False, exit_code=-1, log_id=log_id, tail=str(e))


def _finalize_and_log(command: str, res: Dict[str, Any]) -> Dict[str, Any]:
    """Write command execution details & formatted feedback to the session log file automatically."""
    writeToFile(f"Command Executed: {command}")
    writeToFile(f"Command Result:\n{res}")
    writeToFile(f"Feedback:\n{format_result(res)}")
    return res


def executeCommand(
    command: str, is_interactive: bool = False, timeout: int = 30, background: bool = False
    ) -> Dict[str, Any]:
    os_name = os_family()
    if not isinstance(command, str) or not command.strip():
        return _finalize_and_log(str(command), _result(os_name, success=False, type="static", exit_code=-1, tail="Empty command."))

    # Allow model to inspect any of the last 4 stored command logs via `read_log` or `read_log <id>`
    m = re.match(r"^read_log(?:\s+#?(\d+))?$", command.strip(), re.I)
    if m:
        target_id = int(m.group(1)) if m.group(1) else None
        return _finalize_and_log(command, _result(os_name, success=True, type="log_inspect", exit_code=0, tail=get_command_log(target_id)))

    command = _sanitize_command(command)

    if reason := _check_safety(command):
        log_id = _record_log(command, "blocked", -1, reason)
        return _finalize_and_log(command, _result(os_name, success=False, type="static", exit_code=-1, log_id=log_id, tail=reason))

    if dup_msg := _check_duplicate_locker(command, os_name):
        log_id = _record_log(command, "already_running", 0, dup_msg)
        return _finalize_and_log(command, _result(os_name, success=True, type="background", running=True, log_id=log_id, tail=dup_msg))

    command, is_interactive, background = _classify_execution(command, os_name, is_interactive, background)
    if background:
        res = _run_background(command, os_name, GRACE_SECONDS)
    elif is_interactive and has_display():
        res = _run_interactive(command, os_name)
    else:
        res = _run_headless(command, timeout, os_name)

    return _finalize_and_log(command, res)


def format_result(r: Dict[str, Any]) -> str:
    kind = r.get("type")
    if kind == "log_inspect":
        return r.get("tail", "(empty log)")

    avail_ids = ", ".join(f"#{x['id']}" for x in _log_history) or "none"
    header = f"[Log #{r.get('log_id', '?')} | saved: {avail_ids}]"
    tail = r.get("tail") or "(no output yet)"

    if kind == "background":
        if r.get("running"):
            return f"{header} STATUS: INITIALIZED & RUNNING (pid {r.get('pid', 'active')})\nLines:\n{tail}"
        return f"{header} STATUS: EXITED (code={r.get('exit_code')})\nLines:\n{tail}"

    state = "SUCCEEDED" if r.get("success") else f"EXITED (code={r.get('exit_code', -1)})"
    hint = "\n(Run `read_log <id>` if you need the full log to diagnose.)" if not r.get("success") else ""
    return f"{header} STATUS: {state}\nLines:\n{tail}{hint}"