from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import winreg
import json
import ctypes
from uuid import UUID
from pathlib import Path
from tkinter import DoubleVar, Tk, Toplevel, StringVar, messagebox, ttk


APP_NAME = "TheraTrak Pro"
APP_EXE = "TheraTrak Pro.exe"
UNINSTALL_EXE = "TheraTrak Pro Uninstaller.exe"
APP_BUNDLE_DIR = "app"
UNINSTALL_CMD = "Uninstall TheraTrak Pro.cmd"
ICON_FILE = "Theratrak-Pro.ico"
VERSION_FILE = "version.json"
LEGACY_START_MENU_FOLDERS = ("Thorough Track Pro", "TheraTrak-Pro")
LEGACY_ROOT_SHORTCUTS = ("TheraTrak Pro.lnk", "Uninstall TheraTrak Pro.lnk")


def _find_bundled_python_dll(app_bundle_dir: Path) -> Path | None:
    """Return the path relative to app_bundle_dir of the Python runtime DLL.

    PyInstaller places the DLL inside _internal/  (e.g. python311.dll or
    python312.dll depending on the build Python version).  Probing for it
    at runtime avoids a hardcoded version number that breaks if the build
    environment is ever upgraded.
    """
    internal = app_bundle_dir / "_internal"
    if internal.is_dir():
        for dll in sorted(internal.glob("python3*.dll")):
            return Path("_internal") / dll.name
    return None


def _is_app_running() -> bool:
    """Return True if TheraTrak Pro.exe has any running instances."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {APP_EXE}", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return APP_EXE.lower() in result.stdout.lower()
    except OSError:
        return False


def _stop_running_app() -> None:
    # Best-effort stop so install can replace locked binaries.
    try:
        subprocess.run(
            ["taskkill", "/IM", APP_EXE, "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        pass


def _wait_for_app_exit(timeout: float = 10.0) -> bool:
    """Wait up to *timeout* seconds for TheraTrak Pro to fully exit.

    Returns True when the process is gone, False if it is still running
    after the timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_app_running():
            return True
        time.sleep(0.5)
    return not _is_app_running()


def _is_skippable_shutil_error(ex: shutil.Error) -> bool:
    """Return True if copytree failed only on locked files that already exist at destination."""
    details = ex.args[0] if ex.args and isinstance(ex.args[0], list) else []
    if not details:
        return False
    for item in details:
        if not isinstance(item, tuple) or len(item) < 3:
            return False
        _src, dst, msg = item[0], item[1], str(item[2])
        if "permission denied" not in msg.lower():
            return False
        try:
            if not Path(dst).exists():
                return False
        except OSError:
            return False
    return True


def _copy_with_retries(src: Path, dst: Path, attempts: int = 8) -> None:
    for attempt in range(1, attempts + 1):
        try:
            if src.is_dir():
                if dst.exists():
                    if not dst.is_dir() or dst.is_symlink():
                        dst.unlink(missing_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return
        except PermissionError:
            if attempt >= attempts:
                raise
            _stop_running_app()
            time.sleep(0.75)
        except shutil.Error as ex:
            # copytree can raise shutil.Error when one or more files are locked.
            # If locked files already exist at destination, keep install moving.
            if _is_skippable_shutil_error(ex):
                return
            if attempt >= attempts:
                raise ex
            _stop_running_app()
            time.sleep(0.75)
        except OSError:
            if attempt >= attempts:
                raise
            _stop_running_app()
            time.sleep(1.5)


def _copy_app_bundle_with_progress(
    app_bundle: Path,
    target: Path,
    progress_cb,
) -> None:
    """Copy bundled app payload file-by-file so progress updates stay responsive."""
    file_pairs: list[tuple[Path, Path]] = []

    for item in sorted(app_bundle.iterdir(), key=lambda p: p.name.lower()):
        dst_item = target / item.name
        if item.is_dir():
            dst_item.mkdir(parents=True, exist_ok=True)
            for root, dirnames, filenames in os.walk(item):
                dirnames.sort()
                filenames.sort()
                root_path = Path(root)
                rel_root = root_path.relative_to(item)
                for dirname in dirnames:
                    (dst_item / rel_root / dirname).mkdir(parents=True, exist_ok=True)
                for filename in filenames:
                    src_file = root_path / filename
                    dst_file = dst_item / rel_root / filename
                    file_pairs.append((src_file, dst_file))
        else:
            file_pairs.append((item, dst_item))

    total_files = max(1, len(file_pairs))
    for index, (src_file, dst_file) in enumerate(file_pairs, start=1):
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        _copy_with_retries(src_file, dst_file)
        if index == 1 or index == total_files or index % 25 == 0:
            progress_cb(index, total_files, src_file.name)


def bundled_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def install_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME


def start_menu_program_dirs() -> list[Path]:
    candidates = [
        Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ["ProgramData"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    seen = set()
    unique = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def desktop_dir() -> Path:
    # Resolve real desktop location (works with OneDrive and folder redirection).
    folder_id = UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
    guid_bytes = folder_id.bytes_le

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    guid = GUID(
        int.from_bytes(guid_bytes[0:4], "little"),
        int.from_bytes(guid_bytes[4:6], "little"),
        int.from_bytes(guid_bytes[6:8], "little"),
        (ctypes.c_ubyte * 8).from_buffer_copy(guid_bytes[8:16]),
    )

    path_ptr = ctypes.c_wchar_p()
    hr = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid),
        0,
        None,
        ctypes.byref(path_ptr),
    )
    if hr == 0 and path_ptr.value:
        desktop = Path(path_ptr.value)
        ctypes.windll.ole32.CoTaskMemFree(path_ptr)
        return desktop
    return Path.home() / "Desktop"


def get_display_version(version_path: Path) -> str:
    if not version_path.exists():
        return "1.0.0"
    try:
        with version_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        major = int(data.get("major", 1))
        minor = int(data.get("minor", 0))
        patch = int(data.get("patch", 0))
        build = int(data.get("build", 1))
        return f"{major}.{minor}.{patch}.{build}"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return "1.0.0"


def create_shortcut(
    shortcut_path: Path,
    target_path: Path,
    icon_path: Path,
    working_dir: Path,
    arguments: str = "",
) -> None:
    def _ps_quote(p: Path) -> str:
        return str(p).replace("'", "''")

    if shortcut_path.exists():
        shortcut_path.unlink()

    ps = f"""
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut('{_ps_quote(shortcut_path)}')
$shortcut.TargetPath = '{_ps_quote(target_path)}'
$shortcut.WorkingDirectory = '{_ps_quote(working_dir)}'
$shortcut.IconLocation = '{_ps_quote(icon_path)},0'
$shortcut.Arguments = '{arguments.replace("'", "''")}'
$shortcut.Description = '{APP_NAME}'
$shortcut.Save()
""".strip()
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def write_uninstall_cmd(target: Path) -> Path:
    uninstall_cmd = target / UNINSTALL_CMD
    script = (
        "@echo off\n"
        "setlocal\n"
        "set \"LOG=%TEMP%\\theratrak-uninstall.log\"\n"
        "echo [%date% %time%] Uninstall started>\"%LOG%\"\n"
        "cd /d \"%~dp0\"\n"
        "echo [%date% %time%] Working dir: %cd%>>\"%LOG%\"\n"
        "taskkill /IM \"TheraTrak Pro.exe\" /F >>\"%LOG%\" 2>&1\n"
        "for %%P in (\"%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\" \"%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\" \"%USERPROFILE%\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\") do (\n"
        "  echo [%date% %time%] Cleaning Programs root: %%~P>>\"%LOG%\"\n"
        "  del /f /q \"%%~P\\TheraTrak Pro.lnk\" >>\"%LOG%\" 2>&1\n"
        "  del /f /q \"%%~P\\Uninstall TheraTrak Pro.lnk\" >>\"%LOG%\" 2>&1\n"
        "  rmdir /s /q \"%%~P\\TheraTrak Pro\" >>\"%LOG%\" 2>&1\n"
        "  rmdir /s /q \"%%~P\\Thorough Track Pro\" >>\"%LOG%\" 2>&1\n"
        "  rmdir /s /q \"%%~P\\TheraTrak-Pro\" >>\"%LOG%\" 2>&1\n"
        ")\n"
        "del /f /q \"%USERPROFILE%\\Desktop\\TheraTrak Pro.lnk\" >>\"%LOG%\" 2>&1\n"
        "if defined OneDrive del /f /q \"%OneDrive%\\Desktop\\TheraTrak Pro.lnk\" >>\"%LOG%\" 2>&1\n"
        "rmdir /s /q \"%LOCALAPPDATA%\\Temp\\TheraTrakUpdates\" >>\"%LOG%\" 2>&1\n"
        "del /f /q \"%LOCALAPPDATA%\\Temp\\run_theratrak_update.bat\" >>\"%LOG%\" 2>&1\n"
        "reg delete \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TheraTrak Pro\" /f >>\"%LOG%\" 2>&1\n"
        "reg delete \"HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TheraTrak Pro\" /f >>\"%LOG%\" 2>&1\n"
        "echo [%date% %time%] Refreshing Start menu host>>\"%LOG%\"\n"
        "taskkill /IM StartMenuExperienceHost.exe /F >>\"%LOG%\" 2>&1\n"
        "taskkill /IM explorer.exe /F >>\"%LOG%\" 2>&1\n"
        "start \"\" explorer.exe\n"
        "set \"TARGET=%~dp0\"\n"
        "set \"CLEANUP=%TEMP%\\theratrak_uninstall_cleanup.cmd\"\n"
        ">\"%CLEANUP%\" echo @echo off\n"
        ">>\"%CLEANUP%\" echo set TARGET=%%~1\n"
        ">>\"%CLEANUP%\" echo for /L %%%%i in ^(1,1,20^) do ^(\n"
        ">>\"%CLEANUP%\" echo   rmdir /s /q \"%%TARGET%%\" ^>^>\"%%TEMP%%\\theratrak-uninstall.log\" 2^>^&1\n"
        ">>\"%CLEANUP%\" echo   if not exist \"%%TARGET%%\" goto done\n"
        ">>\"%CLEANUP%\" echo   ping 127.0.0.1 -n 2 ^>nul\n"
        ">>\"%CLEANUP%\" echo ^)\n"
        ">>\"%CLEANUP%\" echo :done\n"
        ">>\"%CLEANUP%\" echo del /f /q \"%%~f0\"\n"
        "start \"\" /min cmd /c \"\"%CLEANUP%\" \"%TARGET%\"\"\n"
        "exit /b 0\n"
    )
    uninstall_cmd.write_text(script, encoding="utf-8", newline="\r\n")
    return uninstall_cmd


def write_uninstall_registry(target: Path, uninstall_cmd: Path, version: str) -> None:
    uninstall_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TheraTrak Pro"
    app_exe = target / APP_EXE
    comspec = Path(os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"))
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, uninstall_path)
    try:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "TheraTrak")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(target))
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(app_exe))
        winreg.SetValueEx(
            key,
            "UninstallString",
            0,
            winreg.REG_SZ,
            f'"{comspec}" /c ""{uninstall_cmd}""',
        )
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    finally:
        winreg.CloseKey(key)


def main() -> int:
    # Enable per-monitor DPI awareness before creating the Tk root so the
    # installer window is sized correctly on HiDPI displays.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)   # ensure all dialogs appear in front

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    proceed = messagebox.askyesno(
        APP_NAME,
        "This will install TheraTrak Pro on your computer.\n\n"
        "Do you want to continue?",
        parent=root,
    )
    if not proceed:
        messagebox.showinfo(APP_NAME, "Installation canceled.", parent=root)
        root.destroy()
        return 0

    progress_window = Toplevel(root)
    progress_window.title(f"Installing {APP_NAME}")
    progress_window.resizable(False, False)
    progress_window.attributes("-topmost", True)
    progress_window.protocol("WM_DELETE_WINDOW", lambda: None)

    status_var = StringVar(value="Preparing installer...")
    status_label = ttk.Label(progress_window, textvariable=status_var, width=56)
    status_label.pack(padx=16, pady=(14, 8))

    progress_var = DoubleVar(value=0)
    progress_bar = ttk.Progressbar(
        progress_window,
        orient="horizontal",
        mode="determinate",
        length=460,
        maximum=100,
        variable=progress_var,
    )
    progress_bar.pack(padx=16, pady=(0, 14))

    progress_window.update_idletasks()
    win_w = max(500, progress_window.winfo_reqwidth() + 8)
    win_h = max(120, progress_window.winfo_reqheight() + 8)
    win_x = max(0, (screen_w - win_w) // 2)
    win_y = max(0, (screen_h - win_h) // 2)
    progress_window.geometry(f"{win_w}x{win_h}+{win_x}+{win_y}")
    progress_window.deiconify()
    progress_window.lift()
    progress_window.focus_force()
    progress_window.update()

    def set_progress(percent: float, status: str) -> None:
        progress_var.set(max(0, min(100, percent)))
        status_var.set(status)
        progress_window.update()

    source = bundled_dir()
    target = install_dir()

    # If TheraTrak Pro is currently open, ask the user to let the installer
    # close it.  Attempting to overwrite locked DLLs inside _internal/ causes
    # WinError 32 (sharing violation) on the copy step.
    if _is_app_running():
        progress_window.destroy()
        close_it = messagebox.askyesno(
            APP_NAME,
            "TheraTrak Pro is currently open.\n\n"
            "It must be closed before the installer can update the files.\n"
            "Click Yes to close it automatically and continue, or No to cancel.",
            parent=root,
        )
        if not close_it:
            messagebox.showinfo(APP_NAME, "Installation canceled.", parent=root)
            root.destroy()
            return 0
        _stop_running_app()
        # Recreate progress window
        progress_window = Toplevel(root)
        progress_window.title(f"Installing {APP_NAME}")
        progress_window.resizable(False, False)
        progress_window.attributes("-topmost", True)
        progress_window.protocol("WM_DELETE_WINDOW", lambda: None)
        status_var2 = StringVar(value="Waiting for TheraTrak Pro to close...")
        ttk.Label(progress_window, textvariable=status_var2, width=56).pack(padx=16, pady=(14, 8))
        progress_var2 = DoubleVar(value=0)
        progress_bar2 = ttk.Progressbar(
            progress_window, orient="horizontal", mode="indeterminate", length=460
        )
        progress_bar2.pack(padx=16, pady=(0, 14))
        progress_window.update_idletasks()
        win_w2 = max(500, progress_window.winfo_reqwidth() + 8)
        win_h2 = max(120, progress_window.winfo_reqheight() + 8)
        progress_window.geometry(
            f"{win_w2}x{win_h2}+{max(0,(screen_w-win_w2)//2)}+{max(0,(screen_h-win_h2)//2)}"
        )
        progress_window.deiconify()
        progress_window.lift()
        progress_window.update()
        progress_bar2.start(10)
        # Poll until process exits (up to 15 s), keeping the UI alive.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and _is_app_running():
            progress_window.update()
            time.sleep(0.25)
        progress_bar2.stop()
        progress_window.destroy()
        if _is_app_running():
            messagebox.showerror(
                APP_NAME,
                "TheraTrak Pro could not be closed automatically.\n"
                "Please close it manually and run the installer again.",
                parent=root,
            )
            root.destroy()
            return 1
        # Rebuild the real progress window now that the app is gone.
        progress_window = Toplevel(root)
        progress_window.title(f"Installing {APP_NAME}")
        progress_window.resizable(False, False)
        progress_window.attributes("-topmost", True)
        progress_window.protocol("WM_DELETE_WINDOW", lambda: None)
        status_var = StringVar(value="Preparing installation folders...")
        status_label = ttk.Label(progress_window, textvariable=status_var, width=56)
        status_label.pack(padx=16, pady=(14, 8))
        progress_var = DoubleVar(value=0)
        progress_bar = ttk.Progressbar(
            progress_window,
            orient="horizontal",
            mode="determinate",
            length=460,
            maximum=100,
            variable=progress_var,
        )
        progress_bar.pack(padx=16, pady=(0, 14))
        progress_window.update_idletasks()
        win_w = max(500, progress_window.winfo_reqwidth() + 8)
        win_h = max(120, progress_window.winfo_reqheight() + 8)
        progress_window.geometry(
            f"{win_w}x{win_h}+{max(0,(screen_w-win_w)//2)}+{max(0,(screen_h-win_h)//2)}"
        )
        progress_window.deiconify()
        progress_window.lift()
        progress_window.focus_force()
        progress_window.update()

        def set_progress(percent: float, status: str) -> None:  # type: ignore[no-redef]
            progress_var.set(max(0, min(100, percent)))
            status_var.set(status)
            progress_window.update()

    set_progress(5, "Preparing installation folders...")
    target.mkdir(parents=True, exist_ok=True)

    app_bundle = source / APP_BUNDLE_DIR
    set_progress(10, "Validating installer payload...")
    python_dll_rel = _find_bundled_python_dll(app_bundle)
    if python_dll_rel is None:
        progress_window.destroy()
        messagebox.showerror(
            APP_NAME,
            "Install failed. Installer payload is incomplete (missing _internal\\python3xx.dll).\n"
            "Please download the installer again.",
        )
        root.destroy()
        return 1

    try:
        if app_bundle.exists() and app_bundle.is_dir():
            def _on_copy_progress(index: int, total: int, file_name: str) -> None:
                set_progress(
                    10 + (50 * (index / total)),
                    f"Copying app files ({index}/{total}): {file_name}",
                )

            _copy_app_bundle_with_progress(app_bundle, target, _on_copy_progress)
            set_progress(60, "Application files copied.")
    except Exception as ex:
        progress_window.destroy()
        messagebox.showerror(
            APP_NAME,
            "Install failed while copying application files.\n"
            "Please close TheraTrak Pro and retry.\n\n"
            f"Details: {ex}",
        )
        root.destroy()
        return 1

    set_progress(65, "Copying installer support files...")
    for name in (UNINSTALL_EXE, ICON_FILE, VERSION_FILE):
        src = source / name
        if src.exists():
            _copy_with_retries(src, target / name)

    exe_path = target / APP_EXE
    uninstaller_path = target / UNINSTALL_EXE
    icon_path = target / ICON_FILE
    target_python_dll = target / python_dll_rel
    uninstall_cmd_path = target / UNINSTALL_CMD

    # Extra safeguard: if the runtime DLL is still missing, try one focused recopy.
    if not target_python_dll.exists():
        set_progress(70, "Verifying runtime components...")
        src_internal = app_bundle / "_internal"
        if src_internal.exists() and src_internal.is_dir():
            _copy_with_retries(src_internal, target / "_internal")

    required = [
        (APP_EXE, exe_path),
        (UNINSTALL_EXE, uninstaller_path),
        (ICON_FILE, icon_path),
        (str(python_dll_rel).replace("/", "\\"), target_python_dll),
    ]
    missing = [label for label, p in required if not p.exists()]
    if missing:
        progress_window.destroy()
        messagebox.showerror(APP_NAME, f"Install failed. Missing files: {', '.join(missing)}")
        root.destroy()
        return 1

    set_progress(75, "Registering uninstall command...")
    uninstall_cmd_path = write_uninstall_cmd(target)

    set_progress(82, "Cleaning old shortcuts...")
    desktop = desktop_dir()
    programs_dirs = start_menu_program_dirs()
    for programs_dir in programs_dirs:
        for legacy_name in (APP_NAME, *LEGACY_START_MENU_FOLDERS):
            legacy_dir = programs_dir / legacy_name
            if legacy_dir.exists() and legacy_dir.is_dir():
                shutil.rmtree(legacy_dir, ignore_errors=True)
        for shortcut_name in LEGACY_ROOT_SHORTCUTS:
            try:
                (programs_dir / shortcut_name).unlink(missing_ok=True)
            except OSError:
                pass

    start_menu_dir = programs_dirs[0] / APP_NAME
    start_menu_dir.mkdir(parents=True, exist_ok=True)

    set_progress(90, "Creating desktop and Start Menu shortcuts...")
    create_shortcut(desktop / f"{APP_NAME}.lnk", exe_path, exe_path, target)
    create_shortcut(start_menu_dir / f"{APP_NAME}.lnk", exe_path, exe_path, target)
    create_shortcut(
        start_menu_dir / "Uninstall TheraTrak Pro.lnk",
        Path(os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe")),
        uninstaller_path,
        target,
        arguments=f'/c ""{uninstall_cmd_path}""',
    )
    set_progress(97, "Writing uninstall registry entries...")
    write_uninstall_registry(target, uninstall_cmd_path, get_display_version(target / VERSION_FILE))
    set_progress(100, "Installation complete.")
    progress_window.destroy()

    messagebox.showinfo(
        APP_NAME,
        "TheraTrak Pro was installed successfully.\n\nDesktop and Start Menu shortcuts were created.\nAn uninstaller was also registered in Installed Apps.",
    )
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())