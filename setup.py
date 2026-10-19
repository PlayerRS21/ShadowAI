import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

TARGET_MAJOR = 3
TARGET_MINOR = 14
TARGET_VERSION_TUPLE = (TARGET_MAJOR, TARGET_MINOR, 0)
VENV_NAME = ".shadowAI"

# ---------------------------------------------------------------------------
# OS & Environment Diagnostics
# ---------------------------------------------------------------------------

def detect_os() -> str:
    """Returns normalized OS identification string."""
    system = platform.system().lower()
    if system == "linux":
        # Distinguish Linux flavors via /etc/os-release
        if Path("/etc/os-release").exists():
            with open("/etc/os-release", "r") as f:
                content = f.read().lower()
                if "arch" in content or "garuda" in content or "manjaro" in content:
                    return "arch"
                elif "ubuntu" in content or "debian" in content or "pop" in content:
                    return "debian"
                elif "fedora" in content or "rhel" in content:
                    return "fedora"
        return "linux_generic"
    elif system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    return "unknown"


def is_python_sufficient() -> bool:
    """Checks if currently executing Python satisfies target version."""
    return sys.version_info >= TARGET_VERSION_TUPLE


def is_inside_shadow_venv() -> bool:
    """Checks if running inside the active .shadowAI virtual environment."""
    current_prefix = Path(sys.prefix).resolve()
    target_venv_path = Path(VENV_NAME).resolve()
    
    # Verify prefix mismatch AND check if prefix path matches .shadowAI
    is_in_any_venv = (sys.prefix != sys.base_prefix) or ("VIRTUAL_ENV" in os.environ)
    is_in_target = current_prefix == target_venv_path
    
    return is_in_any_venv and is_in_target


def get_venv_python_bin(venv_path: Path) -> Path:
    """Retrieves path to the python executable inside the venv across platforms."""
    if platform.system().lower() == "windows":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"

# ---------------------------------------------------------------------------
# OS-Specific Python 3.14 Installation Handlers
# ---------------------------------------------------------------------------

def install_python_arch():
    print("[+] Arch-based distribution detected. Updating system package index...")
    subprocess.run(["sudo", "pacman", "-Syu", "--noconfirm"], check=True)
    print("[+] Installing Python 3.14 via pacman...")
    subprocess.run(["sudo", "pacman", "-S", "python", "python-pip", "--noconfirm"], check=True)


def install_python_debian():
    print("[+] Debian/Ubuntu/Pop!_OS detected. Updating APT cache...")
    subprocess.run(["sudo", "apt", "update"], check=True)
    
    # Try installing direct python3.14 or python3 package
    try:
        subprocess.run(["sudo", "apt", "install", "-y", "python3.14", "python3.14-venv", "python3-pip"], check=True)
    except subprocess.CalledProcessError:
        print("[!] Native package python3.14 not available directly in base apt repo. Adding deadsnakes PPA...")
        subprocess.run(["sudo", "apt", "install", "-y", "software-properties-common"], check=True)
        subprocess.run(["sudo", "add-apt-repository", "-y", "ppa:deadsnakes/ppa"], check=True)
        subprocess.run(["sudo", "apt", "update"], check=True)
        subprocess.run(["sudo", "apt", "install", "-y", "python3.14", "python3.14-venv"], check=True)


def install_python_fedora():
    print("[+] Fedora detected. Updating DNF repositories...")
    subprocess.run(["sudo", "dnf", "install", "-y", "python3.14", "python3-pip"], check=True)


def install_python_macos():
    print("[+] macOS detected. Checking for Homebrew...")
    if not shutil.which("brew"):
        raise RuntimeError("Homebrew is required on macOS. Install Homebrew first from https://brew.sh")
    print("[+] Installing Python 3.14 via Homebrew...")
    subprocess.run(["brew", "install", "python@3.14"], check=True)


def install_python_windows():
    print("[+] Windows detected.")
    # Check if py launcher is installed
    if shutil.which("py"):
        print("[+] Requesting Python 3.14 installation via Windows Python Launcher...")
        subprocess.run(["py", "install", f"{TARGET_MAJOR}.{TARGET_MINOR}"], check=True)
    else:
        print(f"[!] Please download and install Python {TARGET_MAJOR}.{TARGET_MINOR} from https://www.python.org/downloads/")
        sys.exit(1)


def trigger_os_python_installer(os_type: str):
    """Routes execution to system package manager installers."""
    print(f"\n[!] Python version is < {TARGET_MAJOR}.{TARGET_MINOR}. Initiating OS installation routines...\n")
    
    handlers = {
        "arch": install_python_arch,
        "debian": install_python_debian,
        "fedora": install_python_fedora,
        "macos": install_python_macos,
        "windows": install_python_windows,
    }
    
    installer = handlers.get(os_type)
    if installer:
        installer()
    else:
        raise OSError(f"Unsupported or unrecognized system architecture: {os_type}")

# ---------------------------------------------------------------------------
# Core Installation Orchestration
# ---------------------------------------------------------------------------

def run_os_installer_workflow(os_type: str):
    print(f"[✓] OS Profile Identified: {os_type.upper()}")
    
    # 1. Version Check
    if not is_python_sufficient():
        print(f"[!] Current Python version ({sys.version.split()[0]}) is less than {TARGET_MAJOR}.{TARGET_MINOR}")
        trigger_os_python_installer(os_type)
        print("\n[✓] System Python updated. Restart script using new Python binary.")
        sys.exit(0)
    else:
        print(f"[✓] Python version check passed: {sys.version.split()[0]} >= {TARGET_MAJOR}.{TARGET_MINOR}")

    # 2. Virtual Environment Check & Construction
    venv_dir = Path(VENV_NAME).resolve()
    
    if not is_inside_shadow_venv():
        print(f"[!] Not running inside target environment '{VENV_NAME}'.")
        
        if not venv_dir.exists():
            print(f"[+] Creating virtual environment '{VENV_NAME}' using {sys.executable}...")
            import venv
            builder = venv.EnvBuilder(with_pip=True)
            builder.create(venv_dir)
            print(f"[✓] Virtual environment '.shadowAI' successfully instantiated.")
        else:
            print(f"[✓] Found existing '{VENV_NAME}' environment at {venv_dir}")

        # 3. Re-execute current script inside .shadowAI
        venv_python = get_venv_python_bin(venv_dir)
        print(f"[+] Elevating script context to '.shadowAI' -> ({venv_python})")
        print("-" * 60)
        
        result = subprocess.run([str(venv_python)] + sys.argv)
        sys.exit(result.returncode)

    # -----------------------------------------------------------------------
    # Isolated Execution Environment (Only reached when running INSIDE .shadowAI)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"[✓] INSTALLATION TARGET REACHED")
    print(f"    Active Environment : {VENV_NAME}")
    print(f"    Interpreter Path   : {sys.executable}")
    print(f"    Active Python      : {sys.version.split()[0]}")
    print("=" * 60 + "\n")
    
    # Execute payload / dependency installations
    if Path("requirements.txt").exists():
        print("[+] Installing packages from requirements.txt into .shadowAI...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    print()
    print("[✓] Shadow AI Installer completed successfully.")


def main():
    detected_os = detect_os()
    run_os_installer_workflow(detected_os)
    print()
    print("[+] Creating Configs: ")
    print()
    gemini_api=input("Enter your google gemini api key from 'https://aistudio.google.com/api-keys': ")
    print()
    openrouter_api=input("Enter your openrouter api key from 'https://openrouter.ai/': ")
    print()
    groq_api=input("Enter your groq api key fron 'https://console.groq.com/home': ")
    print()
    fish_api=input("Enter your fish audio api key fron 'https://fish.audio/app/api-keys/': ")
    print()
    
    if not gemini_api:
        print("Gemini API key not provided may affect the performance and uptime")

    if not openrouter_api:
        print("OpenRouter API key not provided may affect the performance and uptime")

    if not groq_api:
        print("GROQ API key not provided may affect the performance and uptime")

    if not fish_api:
        print("Fish Audio API key not provided may affect the user experience")
            
    with open(".env","w") as f:
        txt=f"GEMINI_API_KEY={gemini_api}\nOPENROUTER_API_KEY={openrouter_api}\nGROQ_API_KEY={groq_api}\nFISH_AUDIO_API_KEY={fish_api}"
        f.write(txt)

    print("[✓] Config Generated")

    print("[✓] Setup Successful")
    print("Run the app using 'python3 main.py'")

if __name__ == "__main__":
    main()
