import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

# Minimum Python requirement based on standard library imports (zoneinfo, modern typing)
MIN_MAJOR = 3
MIN_MINOR = 10
MIN_VERSION_TUPLE = (MIN_MAJOR, MIN_MINOR, 0)
VENV_NAME = ".shadowAI"

# ---------------------------------------------------------------------------
# Privilege & Command Execution Utilities
# ---------------------------------------------------------------------------

def is_root() -> bool:
    """Checks if running with root/administrator privileges."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        # Windows platform fallback
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0


def get_sudo_cmd() -> list:
    """Returns elevation prefix if needed and available."""
    if is_root() or platform.system().lower() == "windows":
        return []
    if shutil.which("sudo"):
        return ["sudo"]
    return []


def run_command(cmd: list, check: bool = False, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Safely executes sub-commands with error capture."""
    try:
        return subprocess.run(
            cmd,
            check=check,
            text=True,
            capture_output=capture_output
        )
    except Exception as e:
        print(f"[!] Subprocess execution failed for {' '.join(cmd)}: {e}")
        return subprocess.CompletedProcess(args=cmd, returncode=1)

# ---------------------------------------------------------------------------
# OS & Environment Diagnostics
# ---------------------------------------------------------------------------

def detect_os() -> str:
    """Returns normalized OS identification string including Android/Termux."""
    if "TERMUX_VERSION" in os.environ or Path("/data/data/com.termux").exists():
        return "termux"

    system = platform.system().lower()
    if system == "linux":
        if Path("/etc/os-release").exists():
            with open("/etc/os-release", "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
                if any(k in content for k in ["arch", "garuda", "manjaro", "endeavouros"]):
                    return "arch"
                elif any(k in content for k in ["ubuntu", "debian", "pop", "mint", "kali"]):
                    return "debian"
                elif any(k in content for k in ["fedora", "rhel", "centos", "rocky", "alma"]):
                    return "fedora"
                elif "opensuse" in content or "suse" in content:
                    return "suse"
        return "linux_generic"
    elif system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    return "unknown"


def is_python_sufficient() -> bool:
    """Checks if currently executing Python satisfies minimum version."""
    return sys.version_info >= MIN_VERSION_TUPLE


def is_inside_shadow_venv() -> bool:
    """Checks if running inside the active .shadowAI virtual environment."""
    current_prefix = Path(sys.prefix).resolve()
    target_venv_path = Path(VENV_NAME).resolve()

    is_in_any_venv = (sys.prefix != sys.base_prefix) or ("VIRTUAL_ENV" in os.environ)
    is_in_target = current_prefix == target_venv_path

    return is_in_any_venv and is_in_target


def get_venv_python_bin(venv_path: Path) -> Path:
    """Retrieves path to the python executable inside the venv across platforms."""
    if platform.system().lower() == "windows":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"

# ---------------------------------------------------------------------------
# Dynamic System Package & Native C-Library Installers
# ---------------------------------------------------------------------------

def install_system_dependencies(os_type: str):
    """Updates OS indices and installs C-libraries (PortAudio, libsndfile, FFmpeg, build tools)."""
    print(f"\n[+] Updating system package index and installing native C-dependencies for {os_type.upper()}...")
    sudo = get_sudo_cmd()

    if os_type == "arch":
        run_command(sudo + ["pacman", "-Syu", "--noconfirm"])
        run_command(sudo + [
            "pacman", "-S", "--needed", "--noconfirm",
            "base-devel", "portaudio", "libsndfile", "ffmpeg", "alsa-lib", "python-pip"
        ])

    elif os_type == "debian":
        run_command(sudo + ["apt", "update", "-y"])
        # Fix broken packages if apt state was unclean
        run_command(sudo + ["apt", "--fix-broken", "install", "-y"])
        run_command(sudo + [
            "apt", "install", "-y",
            "build-essential", "portaudio19-dev", "libsndfile1-dev",
            "ffmpeg", "libasound2-dev", "python3-pip", "python3-venv", "python3-dev"
        ])

    elif os_type == "fedora":
        run_command(sudo + ["dnf", "check-update"])
        run_command(sudo + [
            "dnf", "install", "-y",
            "gcc", "gcc-c++", "make", "portaudio-devel", "libsndfile-devel",
            "ffmpeg", "alsa-lib-devel", "python3-devel", "python3-pip"
        ])

    elif os_type == "suse":
        run_command(sudo + ["zypper", "refresh"])
        run_command(sudo + [
            "zypper", "install", "-y",
            "devel_basis", "portaudio-devel", "libsndfile-devel",
            "ffmpeg", "alsa-devel", "python3-pip"
        ])

    elif os_type == "macos":
        if not shutil.which("brew"):
            print("[!] Homebrew not found. Attempting non-interactive Homebrew bootstrap...")
            brew_installer = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            run_command(["/bin/bash", "-c", brew_installer])

        if shutil.which("brew"):
            run_command(["brew", "update"])
            run_command(["brew", "install", "portaudio", "libsndfile", "ffmpeg"])

    elif os_type == "termux":
        run_command(["pkg", "update", "-y"])
        run_command(["pkg", "upgrade", "-y"])
        run_command([
            "pkg", "install", "-y",
            "clang", "make", "pkg-config", "portaudio", "libsndfile", "ffmpeg", "python"
        ])

    elif os_type == "windows":
        # Check Winget for native FFmpeg / Build tools if available
        if shutil.which("winget"):
            print("[+] Checking Windows Winget package manager for FFmpeg...")
            run_command(["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements", "--accept-package-agreements"])

# ---------------------------------------------------------------------------
# Core Installation Orchestration
# ---------------------------------------------------------------------------

def ensure_venv_validity(venv_dir: Path) -> Path:
    """Creates or repairs virtual environment reliably."""
    venv_python = get_venv_python_bin(venv_dir)

    # Check if existing venv is broken
    if venv_dir.exists() and not venv_python.exists():
        print(f"[!] Found corrupted virtual environment at {venv_dir}. Recreating...")
        shutil.rmtree(venv_dir, ignore_errors=True)

    if not venv_dir.exists():
        print(f"[+] Instantiating virtual environment '{VENV_NAME}' using {sys.executable}...")
        import venv
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(venv_dir)
        print(f"[✓] Virtual environment '{VENV_NAME}' created successfully.")

    return venv_python


def run_os_installer_workflow(os_type: str):
    print(f"[✓] Identified System Environment Profile: {os_type.upper()}")

    # 1. Version Check
    if not is_python_sufficient():
        current_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(f"[!] Current Python binary ({current_ver}) is below minimum requirement ({MIN_MAJOR}.{MIN_MINOR}+)")
        print(f"[!] Please run this setup using Python {MIN_MAJOR}.{MIN_MINOR} or higher.")
        sys.exit(1)
    else:
        print(f"[✓] Python version verified: {sys.version.split()[0]} >= {MIN_MAJOR}.{MIN_MINOR}")

    # 2. System Level Library Update & Installation
    install_system_dependencies(os_type)

    # 3. Virtual Environment Context Isolation
    venv_dir = Path(VENV_NAME).resolve()

    if not is_inside_shadow_venv():
        print(f"\n[!] Executing outer runtime check. Redirecting into '{VENV_NAME}'...")
        venv_python = ensure_venv_validity(venv_dir)

        # Ensure core packaging tools inside venv are up to date
        print("[+] Upgrading core pip tooling inside environment...")
        run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

        print(f"[+] Re-executing setup context inside '{VENV_NAME}' context...")
        print("=" * 60)
        
        result = subprocess.run([str(venv_python)] + sys.argv)
        sys.exit(result.returncode)

    # -----------------------------------------------------------------------
    # Reached only inside the isolated .shadowAI virtual environment
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"[✓] INSIDE ISOLATED ENVIRONMENT ({VENV_NAME})")
    print(f"    Interpreter Path : {sys.executable}")
    print(f"    Active Version   : {sys.version.split()[0]}")
    print("=" * 60 + "\n")

    if Path("requirements.txt").exists():
        print("[+] Installing Python module dependencies from requirements.txt...")
        
        # Disable cache on failure attempt for build issues
        pip_cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        res = run_command(pip_cmd)
        
        if res.returncode != 0:
            print("[!] Standard pip install encountered issues. Retrying with binary wheels priority...")
            run_command([sys.executable, "-m", "pip", "install", "--prefer-binary", "-r", "requirements.txt"], check=True)
            
        print("[✓] All Python dependencies installed successfully.")
    else:
        print("[!] Warning: requirements.txt was not found in current execution folder.")


def create_env_config():
    """Interactively creates/updates .env configuration securely."""
    print("\n" + "=" * 60)
    print("[+] CONFIGURATION INITIALIZATION (.env)")
    print("=" * 60)

    gemini_api = input("\nEnter Google Gemini API Key (Optional): ").strip()
    openrouter_api = input("Enter OpenRouter API Key (Optional): ").strip()
    groq_api = input("Enter Primary GROQ API Key (Optional): ").strip()
    groq_api2 = input("Enter Secondary GROQ API Key (Optional): ").strip()
    fish_api = input("Enter Fish Audio API Key (Optional): ").strip()
    tavily_api = input("Enter Tavily Search API Key (Optional): ").strip()

    env_content = (
        f"GEMINI_API_KEY={gemini_api}\n"
        f"OPENROUTER_API_KEY={openrouter_api}\n"
        f"GROQ_API_KEY={groq_api}\n"
        f"GROQ_API_KEY2={groq_api2}\n"
        f"FISH_AUDIO_API_KEY={fish_api}\n"
        f"TAVILY_SEARCH_API_KEY={tavily_api}\n"
    )

    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)

    print("\n[✓] Environment file .env successfully saved.")


def main():
    detected_os = detect_os()
    run_os_installer_workflow(detected_os)
    create_env_config()

    print("\n" + "=" * 60)
    print("[✓] SETUP COMPLETE")
    print("=" * 60)
    if platform.system().lower() == "windows":
        print(f"Run application using:\n    .\\{VENV_NAME}\\Scripts\\activate\n    python main.py")
    else:
        print(f"Run application using:\n    source {VENV_NAME}/bin/activate\n    python main.py")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
