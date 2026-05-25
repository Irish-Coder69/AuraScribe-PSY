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
from tkinter import DoubleVar, Tk, Toplevel, StringVar, filedialog, messagebox, ttk


APP_NAME = "Aura Scribe PSY"
APP_EXE = "Aura Scribe PSY.exe"
UNINSTALL_EXE = "Aura Scribe PSY Uninstaller.exe"
APP_BUNDLE_DIR = "app"
UNINSTALL_CMD = "Uninstall Aura Scribe PSY.cmd"
UNINSTALL_SHORTCUT_NAME = "Uninstall Aura Scribe PSY.lnk"
ICON_FILE = "Aura Scribe PSY.ico"
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
    """Return True if the packaged app executable is currently running."""
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
    """Wait up to *timeout* seconds for the app to fully exit.

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


def _can_write_to_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".aurascribe_write_test.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def choose_install_dir(root: Tk, default_path: Path) -> Path | None:
    import tkinter as tk

    # ── Palette ─────────────────────────────────────────────────────────────
    # Header: warm sky-blue gradient (uplifting, open, calming)
    C_GRAD_TOP  = (110, 195, 232)   # #6ec3e8  — light sky blue
    C_GRAD_BOT  = (58,  140, 195)   # #3a8cc3  — medium sky blue
    C_HDR_TEXT  = "#ffffff"
    C_HDR_SUB   = "#d6eef8"
    C_DIVIDER   = "#3a8cc3"
    C_BODY_BG   = "#f5f7fa"
    C_LABEL_FG  = "#1a2535"
    C_SUB_FG    = "#556070"
    C_ENTRY_BG  = "#ffffff"
    C_ENTRY_HI  = "#3a8cc3"
    C_BROWSE_BG = "#ddeef8"
    C_BROWSE_FG = "#1d5f8a"
    C_BTN_INST  = "#3a8cc3"
    C_BTN_CNCL  = "#6b7280"
    C_BTN_FG    = "#ffffff"
    C_BAR_BG    = "#e4ecf4"

    FONT_TITLE  = ("Segoe UI", 17, "bold")
    FONT_SUB    = ("Segoe UI", 9)
    FONT_LABEL  = ("Segoe UI", 10)
    FONT_ENTRY  = ("Segoe UI", 10)
    FONT_BTN    = ("Segoe UI", 10, "bold")
    FONT_BROWSE = ("Segoe UI", 9)

    DIALOG_W = 580
    HEADER_H = 122

    dialog = Toplevel(root)
    dialog.title(f"Install {APP_NAME}")
    dialog.resizable(False, False)
    dialog.configure(bg=C_BODY_BG)
    dialog.attributes("-topmost", True)
    dialog.grab_set()
    dialog.minsize(DIALOG_W, 1)

    # ── Header canvas: gradient + "A-with-waveform" logo ────────────────────
    hdr = tk.Canvas(dialog, width=DIALOG_W, height=HEADER_H, highlightthickness=0)
    hdr.pack(fill="x")

    # Gradient fill
    r0, g0, b0 = C_GRAD_TOP
    r1, g1, b1 = C_GRAD_BOT
    for i in range(HEADER_H):
        t = i / max(1, HEADER_H - 1)
        r = int(r0 + (r1 - r0) * t)
        g = int(g0 + (g1 - g0) * t)
        b = int(b0 + (b1 - b0) * t)
        hdr.create_line(0, i, DIALOG_W, i, fill=f"#{r:02x}{g:02x}{b:02x}")

    # ── Logo: clean thin-lined "A" — crossbar replaced by audio waveform ─────
    #
    #          apex
    #           /\
    #          /  \       ← thin white legs, line-width 1.8
    #         /~~~~\      ← waveform instead of flat crossbar
    #        /      \
    #
    cx   = DIALOG_W // 2    # horizontal centre
    a_y  = 8                # apex y
    b_y  = 52               # bottom y
    hw   = 24               # half-width at bottom

    # left and right legs
    hdr.create_line(cx, a_y, cx - hw, b_y, fill="white", width=1.8,
                    capstyle="round")
    hdr.create_line(cx, a_y, cx + hw, b_y, fill="white", width=1.8,
                    capstyle="round")

    # crossbar position (55 % of the way from apex to base)
    t_c   = 0.55
    wf_y  = a_y + (b_y - a_y) * t_c          # y of the crossbar ≈ 34
    wf_xl = cx - hw * t_c                     # left  leg x at that height
    wf_xr = cx + hw * t_c                     # right leg x at that height

    # Waveform control points (nx in [-1,1], ny: negative = up on screen)
    # Mimics a compact voice waveform — quiet at edges, animated in the middle
    wf_nodes = [
        (-1.00,  0.00),
        (-0.80, -0.30),
        (-0.58, -0.80),
        (-0.36,  0.25),
        (-0.14, -1.00),
        ( 0.08,  0.40),
        ( 0.28, -0.70),
        ( 0.50,  0.20),
        ( 0.72, -0.50),
        ( 0.88, -0.20),
        ( 1.00,  0.00),
    ]
    amp    = 5.0
    wf_pts = []
    span   = wf_xr - wf_xl
    for nx, ny in wf_nodes:
        wf_pts.append(wf_xl + (nx + 1) / 2.0 * span)
        wf_pts.append(wf_y + ny * amp)

    hdr.create_line(*wf_pts, fill="white", width=1.6,
                    smooth=True, capstyle="round", joinstyle="round")

    # App name and subtitle drawn on the canvas
    hdr.create_text(cx, b_y + 18, text=APP_NAME,
                    font=FONT_TITLE, fill=C_HDR_TEXT, anchor="center")
    hdr.create_text(cx, b_y + 40, text="Setup Wizard",
                    font=FONT_SUB, fill=C_HDR_SUB, anchor="center")

    # ── Accent divider ───────────────────────────────────────────────────────
    tk.Frame(dialog, bg=C_DIVIDER, height=3).pack(fill="x")

    # ── Body ─────────────────────────────────────────────────────────────────
    body = tk.Frame(dialog, bg=C_BODY_BG, padx=28, pady=22)
    body.pack(fill="both", expand=True)

    tk.Label(body, text="Choose Installation Folder",
             font=("Segoe UI", 11, "bold"), bg=C_BODY_BG,
             fg=C_LABEL_FG).pack(anchor="w")
    tk.Label(body,
             text="Select where Aura Scribe PSY should be installed on your computer.",
             font=FONT_LABEL, bg=C_BODY_BG, fg=C_SUB_FG).pack(anchor="w",
                                                                pady=(2, 16))

    # ── Path row ─────────────────────────────────────────────────────────────
    path_var  = StringVar(value=str(default_path))
    path_frame = tk.Frame(body, bg=C_BODY_BG)
    path_frame.pack(fill="x")

    tk.Label(path_frame, text="Install to:", font=FONT_LABEL,
             bg=C_BODY_BG, fg=C_LABEL_FG, width=9,
             anchor="w").pack(side="left")

    entry = tk.Entry(path_frame, textvariable=path_var, font=FONT_ENTRY,
                     bg=C_ENTRY_BG, fg=C_LABEL_FG, relief="flat",
                     highlightthickness=1, highlightbackground=C_ENTRY_HI,
                     highlightcolor=C_ENTRY_HI, insertbackground=C_ENTRY_HI,
                     width=44)
    entry.pack(side="left", fill="x", expand=True, ipady=5)

    def _browse() -> None:
        start_dir = Path(path_var.get().strip() or str(default_path))
        selected = filedialog.askdirectory(
            parent=dialog,
            title=f"Select {APP_NAME} install folder",
            initialdir=str(start_dir.parent if start_dir.parent.exists()
                           else start_dir),
            mustexist=False,
        )
        if selected:
            path_var.set(selected)

    tk.Button(path_frame, text="Browse…", font=FONT_BROWSE,
              bg=C_BROWSE_BG, fg=C_BROWSE_FG, relief="flat", cursor="hand2",
              padx=10, pady=5, command=_browse,
              activebackground="#b8d8ef",
              activeforeground=C_BROWSE_FG).pack(side="left", padx=(8, 0))

    tk.Label(body, text="Default: %LOCALAPPDATA%\\Programs\\Aura Scribe PSY",
             font=("Segoe UI", 8), bg=C_BODY_BG,
             fg="#aaaaaa").pack(anchor="w", pady=(6, 0))

    result: dict[str, Path | None] = {"path": None}

    def _install() -> None:
        raw = path_var.get().strip().strip('"')
        if not raw:
            messagebox.showerror(APP_NAME,
                                 "Please choose an installation folder.",
                                 parent=dialog)
            return
        target = Path(raw)
        if target.exists() and target.is_file():
            messagebox.showerror(APP_NAME,
                                 "Install path points to a file, not a folder.",
                                 parent=dialog)
            return
        if not _can_write_to_dir(target):
            messagebox.showerror(APP_NAME,
                                 "Aura Scribe PSY cannot write to this folder.\n"
                                 "Choose another location.",
                                 parent=dialog)
            return
        result["path"] = target
        dialog.destroy()

    def _cancel() -> None:
        dialog.destroy()

    # ── Bottom bar ────────────────────────────────────────────────────────────
    bar = tk.Frame(dialog, bg=C_BAR_BG, pady=12)
    bar.pack(fill="x", side="bottom")

    cancel_btn = tk.Button(bar, text="Cancel", font=FONT_BTN,
                           bg=C_BTN_CNCL, fg=C_BTN_FG, relief="flat",
                           padx=20, pady=7, cursor="hand2", command=_cancel,
                           activebackground="#4b5563",
                           activeforeground=C_BTN_FG)
    cancel_btn.pack(side="right", padx=(0, 20))
    cancel_btn.bind("<Enter>", lambda e: cancel_btn.configure(bg="#4b5563"))
    cancel_btn.bind("<Leave>", lambda e: cancel_btn.configure(bg=C_BTN_CNCL))

    install_btn = tk.Button(bar, text="Install  →", font=FONT_BTN,
                            bg=C_BTN_INST, fg=C_BTN_FG, relief="flat",
                            padx=20, pady=7, cursor="hand2", command=_install,
                            activebackground="#1d5f8a",
                            activeforeground=C_BTN_FG)
    install_btn.pack(side="right", padx=(0, 8))
    install_btn.bind("<Enter>", lambda e: install_btn.configure(bg="#1d5f8a"))
    install_btn.bind("<Leave>", lambda e: install_btn.configure(bg=C_BTN_INST))

    dialog.bind("<Return>", lambda e: _install())
    dialog.bind("<Escape>", lambda e: _cancel())

    # ── Centre on screen ──────────────────────────────────────────────────────
    dialog.update_idletasks()
    w  = max(DIALOG_W, dialog.winfo_reqwidth())
    h  = dialog.winfo_reqheight()
    sx = dialog.winfo_screenwidth()
    sy = dialog.winfo_screenheight()
    dialog.geometry(f"{w}x{h}+{max(0,(sx-w)//2)}+{max(0,(sy-h)//2)}")

    entry.focus_set()
    dialog.deiconify()
    dialog.lift()
    dialog.wait_window()
    return result["path"]


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
        "set \"LOG=%TEMP%\\aurascribe-uninstall.log\"\n"
        "echo [%date% %time%] Uninstall started>\"%LOG%\"\n"
        "cd /d \"%~dp0\"\n"
        "echo [%date% %time%] Working dir: %cd%>>\"%LOG%\"\n"
        f"taskkill /IM \"{APP_EXE}\" /F >>\"%LOG%\" 2>&1\\n"
        "for %%P in (\"%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\" \"%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\" \"%USERPROFILE%\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\") do (\n"
        "  echo [%date% %time%] Cleaning Programs root: %%~P>>\"%LOG%\"\n"
        "  del /f /q \"%%~P\\Aura Scribe PSY.lnk\" >>\"%LOG%\" 2>&1\n"
        "  del /f /q \"%%~P\\Uninstall Aura Scribe PSY.lnk\" >>\"%LOG%\" 2>&1\n"
        "  del /f /q \"%%~P\\TheraTrak Pro.lnk\" >>\"%LOG%\" 2>&1\n"
        "  del /f /q \"%%~P\\Uninstall TheraTrak Pro.lnk\" >>\"%LOG%\" 2>&1\n"
        "  rmdir /s /q \"%%~P\\Aura Scribe PSY\" >>\"%LOG%\" 2>&1\n"
        "  rmdir /s /q \"%%~P\\TheraTrak Pro\" >>\"%LOG%\" 2>&1\n"
        "  rmdir /s /q \"%%~P\\Thorough Track Pro\" >>\"%LOG%\" 2>&1\n"
        "  rmdir /s /q \"%%~P\\TheraTrak-Pro\" >>\"%LOG%\" 2>&1\n"
        ")\n"
        "del /f /q \"%USERPROFILE%\\Desktop\\Aura Scribe PSY.lnk\" >>\"%LOG%\" 2>&1\n"
        "if defined OneDrive del /f /q \"%OneDrive%\\Desktop\\Aura Scribe PSY.lnk\" >>\"%LOG%\" 2>&1\n"
        "del /f /q \"%USERPROFILE%\\Desktop\\TheraTrak Pro.lnk\" >>\"%LOG%\" 2>&1\n"
        "if defined OneDrive del /f /q \"%OneDrive%\\Desktop\\TheraTrak Pro.lnk\" >>\"%LOG%\" 2>&1\n"
        "rmdir /s /q \"%LOCALAPPDATA%\\Temp\\AuraScribePSYUpdates\" >>\"%LOG%\" 2>&1\n"
        "rmdir /s /q \"%LOCALAPPDATA%\\Temp\\TheraTrakUpdates\" >>\"%LOG%\" 2>&1\n"
        "del /f /q \"%LOCALAPPDATA%\\Temp\\run_aurascribe_update.bat\" >>\"%LOG%\" 2>&1\n"
        "del /f /q \"%LOCALAPPDATA%\\Temp\\run_theratrak_update.bat\" >>\"%LOG%\" 2>&1\n"
        "reg delete \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Aura Scribe PSY\" /f >>\"%LOG%\" 2>&1\n"
        "reg delete \"HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Aura Scribe PSY\" /f >>\"%LOG%\" 2>&1\n"
        "reg delete \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TheraTrak Pro\" /f >>\"%LOG%\" 2>&1\n"
        "reg delete \"HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TheraTrak Pro\" /f >>\"%LOG%\" 2>&1\n"
        "echo [%date% %time%] Refreshing Start menu host>>\"%LOG%\"\n"
        "taskkill /IM StartMenuExperienceHost.exe /F >>\"%LOG%\" 2>&1\n"
        "taskkill /IM explorer.exe /F >>\"%LOG%\" 2>&1\n"
        "start \"\" explorer.exe\n"
        "set \"TARGET=%~dp0\"\n"
        "set \"CLEANUP=%TEMP%\\aurascribe_uninstall_cleanup.cmd\"\n"
        ">\"%CLEANUP%\" echo @echo off\n"
        ">>\"%CLEANUP%\" echo set TARGET=%%~1\n"
        ">>\"%CLEANUP%\" echo for /L %%%%i in ^(1,1,20^) do ^(\n"
        ">>\"%CLEANUP%\" echo   rmdir /s /q \"%%TARGET%%\" ^>^>\"%%TEMP%%\\aurascribe-uninstall.log\" 2^>^&1\n"
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
    uninstall_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Aura Scribe PSY"
    app_exe = target / APP_EXE
    comspec = Path(os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"))
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, uninstall_path)
    try:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Aura Scribe PSY")
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


def _build_progress_window(
    root: Tk,
    screen_w: int,
    screen_h: int,
    initial_status: str = "Preparing...",
    indeterminate: bool = False,
) -> tuple:
    """Return (window, set_progress) — a styled progress window matching the installer UI."""
    import tkinter as tk

    C_GRAD_TOP = (110, 195, 232)
    C_GRAD_BOT = (58,  140, 195)
    C_BODY_BG  = "#f5f7fa"
    C_SUB_FG   = "#556070"
    C_BAR_BG   = "#d8e8f2"
    C_DIVIDER  = "#3a8cc3"
    WIN_W      = 520
    HEADER_H   = 62

    win = Toplevel(root)
    win.title(f"Installing {APP_NAME}")
    win.resizable(False, False)
    win.configure(bg=C_BODY_BG)
    win.attributes("-topmost", True)
    win.attributes("-toolwindow", False)
    win.protocol("WM_DELETE_WINDOW", lambda: None)

    # Gradient header
    hdr = tk.Canvas(win, width=WIN_W, height=HEADER_H, highlightthickness=0)
    hdr.pack(fill="x")
    r0, g0, b0 = C_GRAD_TOP
    r1, g1, b1 = C_GRAD_BOT
    for i in range(HEADER_H):
        t = i / max(1, HEADER_H - 1)
        r = int(r0 + (r1 - r0) * t)
        g = int(g0 + (g1 - g0) * t)
        b = int(b0 + (b1 - b0) * t)
        hdr.create_line(0, i, WIN_W, i, fill=f"#{r:02x}{g:02x}{b:02x}")
    hdr.create_text(WIN_W // 2, HEADER_H // 2 - 6, text=APP_NAME,
                    font=("Segoe UI", 14, "bold"), fill="white", anchor="center")
    hdr.create_text(WIN_W // 2, HEADER_H // 2 + 13, text="Installing, please wait…",
                    font=("Segoe UI", 8), fill="#d6eef8", anchor="center")

    tk.Frame(win, bg=C_DIVIDER, height=3).pack(fill="x")

    body = tk.Frame(win, bg=C_BODY_BG, padx=24, pady=18)
    body.pack(fill="both", expand=True)

    status_var = StringVar(value=initial_status)
    tk.Label(body, textvariable=status_var, font=("Segoe UI", 9),
             bg=C_BODY_BG, fg=C_SUB_FG, anchor="w",
             wraplength=WIN_W - 48).pack(anchor="w", pady=(0, 10))

    BAR_W = WIN_W - 48
    BAR_H = 16

    bar_canvas = tk.Canvas(body, width=BAR_W, height=BAR_H,
                           bg=C_BAR_BG, highlightthickness=0)
    bar_canvas.pack(anchor="w")

    if indeterminate:
        _state = {"pos": -(BAR_W // 3), "active": True}
        BLOCK = BAR_W // 4

        def _animate() -> None:
            if not _state["active"]:
                return
            bar_canvas.delete("all")
            bar_canvas.create_rectangle(0, 0, BAR_W, BAR_H, fill=C_BAR_BG, outline="")
            x = _state["pos"]
            x1, x2 = max(0, x), min(x + BLOCK, BAR_W)
            if x1 < x2:
                for px in range(x1, x2):
                    t  = px / max(1, BAR_W - 1)
                    rr = int(110 + (58  - 110) * t)
                    gg = int(195 + (140 - 195) * t)
                    bb = int(232 + (195 - 232) * t)
                    bar_canvas.create_line(px, 0, px, BAR_H,
                                           fill=f"#{rr:02x}{gg:02x}{bb:02x}")
            _state["pos"] = x + 8
            if _state["pos"] > BAR_W:
                _state["pos"] = -BLOCK
            win.after(25, _animate)

        _animate()

        def set_progress(pct: float, status: str) -> None:
            status_var.set(status)
            win.update()

        _orig_destroy = win.destroy

        def _destroy_patched() -> None:
            _state["active"] = False
            _orig_destroy()

        win.destroy = _destroy_patched  # type: ignore[method-assign]

    else:
        pct_label = tk.Label(body, text="0%", font=("Segoe UI", 8),
                             bg=C_BODY_BG, fg=C_SUB_FG, anchor="e")
        pct_label.pack(anchor="e", pady=(3, 0))

        def _draw_bar(pct: float) -> None:
            bar_canvas.delete("all")
            bar_canvas.create_rectangle(0, 0, BAR_W, BAR_H,
                                        fill=C_BAR_BG, outline="")
            filled = int(BAR_W * pct / 100)
            for px in range(filled):
                t  = px / max(1, BAR_W - 1)
                rr = int(110 + (58  - 110) * t)
                gg = int(195 + (140 - 195) * t)
                bb = int(232 + (195 - 232) * t)
                bar_canvas.create_line(px, 0, px, BAR_H,
                                       fill=f"#{rr:02x}{gg:02x}{bb:02x}")

        _draw_bar(0)

        def set_progress(pct: float, status: str) -> None:
            pct = max(0.0, min(100.0, pct))
            _draw_bar(pct)
            pct_label.configure(text=f"{int(pct)}%")
            status_var.set(status)
            win.update()

    win.update_idletasks()
    ww = max(WIN_W, win.winfo_reqwidth())
    wh = win.winfo_reqheight()
    win.geometry(f"{ww}x{wh}+{max(0,(screen_w-ww)//2)}+{max(0,(screen_h-wh)//2)}")
    win.deiconify()
    win.lift()
    win.focus_force()
    win.update()

    return win, set_progress


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

    target = choose_install_dir(root, install_dir())
    if target is None:
        messagebox.showinfo(APP_NAME, "Installation canceled.", parent=root)
        root.destroy()
        return 0

    progress_window, set_progress = _build_progress_window(
        root, screen_w, screen_h, "Preparing installer..."
    )

    source = bundled_dir()

    # If Aura Scribe PSY is currently open, ask the user to let the installer
    # close it.  Attempting to overwrite locked DLLs inside _internal/ causes
    # WinError 32 (sharing violation) on the copy step.
    if _is_app_running():
        progress_window.destroy()
        close_it = messagebox.askyesno(
            APP_NAME,
            "Aura Scribe PSY is currently open.\n\n"
            "It must be closed before the installer can update the files.\n"
            "Click Yes to close it automatically and continue, or No to cancel.",
            parent=root,
        )
        if not close_it:
            messagebox.showinfo(APP_NAME, "Installation canceled.", parent=root)
            root.destroy()
            return 0
        _stop_running_app()
        # Recreate progress window (indeterminate — waiting for app to exit)
        progress_window, _wait_set = _build_progress_window(
            root, screen_w, screen_h,
            "Waiting for Aura Scribe PSY to close...",
            indeterminate=True,
        )
        # Poll until process exits (up to 15 s), keeping the UI alive.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and _is_app_running():
            progress_window.update()
            time.sleep(0.25)
        progress_window.destroy()
        if _is_app_running():
            messagebox.showerror(
                APP_NAME,
                "Aura Scribe PSY could not be closed automatically.\n"
                "Please close it manually and run the installer again.",
                parent=root,
            )
            root.destroy()
            return 1
        # Rebuild the real progress window now that the app is gone.
        progress_window, set_progress = _build_progress_window(  # type: ignore[no-redef]
            root, screen_w, screen_h, "Preparing installation folders..."
        )

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
            "Please close Aura Scribe PSY and retry.\n\n"
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
        start_menu_dir / UNINSTALL_SHORTCUT_NAME,
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
        "Aura Scribe PSY was installed successfully.\n\nDesktop and Start Menu shortcuts were created.\nAn uninstaller was also registered in Installed Apps.",
    )
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())