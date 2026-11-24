import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import tty
from typing import Any, Dict

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _sync_winsize(src_fd: int, dst_fd: int) -> None:
    """Copy terminal rows/columns from real terminal to PTY so progress bars & TUIs render cleanly."""
    try:
        winsize = fcntl.ioctl(src_fd, termios.TIOCGWINSZ, b"\x00" * 8)
        fcntl.ioctl(dst_fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass


def run_in_embedded_pty(command: str, cwd: str) -> Dict[str, Any]:
    """
    Execute a command inside an inline PTY attached to the user's current terminal.
    - Inherits exact terminal theme, colors, and interactive TTY (sudo, fingerprint, pacman, vim, etc.).
    - Tees all output to both the user's screen and a captured buffer for Shadow.
    - Returns exact exit_code and stripped output.
    """
    if sys.platform == "win32":
        return _run_windows_fallback(command, cwd)

    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    has_tty = os.isatty(stdin_fd)

    pid, master_fd = pty.fork()

    if pid == 0:
        # Child process: switch to tracked working directory and exec command
        try:
            os.chdir(cwd)
        except OSError:
            pass
        os.execvp("/bin/bash", ["/bin/bash", "-c", command])

    # Parent process: bridge stdin/stdout and record output
    old_tty_attrs = None
    if has_tty:
        _sync_winsize(stdin_fd, master_fd)
        old_tty_attrs = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)

        # Forward Hyprland/WM window resize signals to the PTY child
        def _on_winch(signum, frame):
            _sync_winsize(stdin_fd, master_fd)
            try:
                os.kill(pid, signal.SIGWINCH)
            except OSError:
                pass

        prev_winch = signal.signal(signal.SIGWINCH, _on_winch)

    captured_chunks = []
    try:
        watch_fds = [master_fd, stdin_fd] if has_tty else [master_fd]
        while True:
            rlist, _, _ = select.select(watch_fds, [], [])
            if master_fd in rlist:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                os.write(stdout_fd, data)
                captured_chunks.append(data)

            if has_tty and stdin_fd in rlist:
                user_bytes = os.read(stdin_fd, 1024)
                if not user_bytes:
                    break
                os.write(master_fd, user_bytes)
    finally:
        if has_tty and old_tty_attrs is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty_attrs)
            signal.signal(signal.SIGWINCH, prev_winch)
        try:
            os.close(master_fd)
        except OSError:
            pass

    _, status = os.waitpid(pid, 0)
    exit_code = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else (
        os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
    )

    raw_text = b"".join(captured_chunks).decode("utf-8", errors="replace")
    clean_text = _strip_ansi(raw_text)

    return {
        "exit_code": exit_code,
        "output": clean_text,
    }


def _run_windows_fallback(command: str, cwd: str) -> Dict[str, Any]:
    """Windows inline fallback (uses pywinpty if installed, else inherits current console)."""
    import subprocess
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return {
        "exit_code": proc.returncode,
        "output": (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else ""),
    }