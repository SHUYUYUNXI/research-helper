# -*- coding: utf-8 -*-
"""Suite-wide containment for tests that exercise user-facing installers."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_reach.config import Config


def _windows_symlink_capable():
    """Inspect permissions without making a potentially blocked filesystem call."""
    import ctypes
    from ctypes import wintypes
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock") as key:
            if winreg.QueryValueEx(key, "AllowDevelopmentWithoutDevLicense")[0] == 1:
                return True
    except OSError:
        pass
    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]
    class Privilege(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]
    token = wintypes.HANDLE()
    needed = wintypes.DWORD()
    wanted = LUID()
    advapi = ctypes.windll.advapi32
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(LUID)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        return None
    try:
        if not advapi.LookupPrivilegeValueW(None, "SeCreateSymbolicLinkPrivilege", ctypes.byref(wanted)):
            return None
        advapi.GetTokenInformation(token, 3, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 3, buffer, needed, ctypes.byref(needed)):
            return None
        count = wintypes.DWORD.from_buffer(buffer).value
        for index in range(count):
            item = Privilege.from_buffer(buffer, ctypes.sizeof(wintypes.DWORD) + index * ctypes.sizeof(Privilege))
            if item.Luid.LowPart == wanted.LowPart and item.Luid.HighPart == wanted.HighPart and item.Attributes & 2:
                return True
        return False
    finally:
        kernel.CloseHandle(token)


@pytest.fixture(scope="session")
def symlink_capability():
    return _windows_symlink_capable() if os.name == "nt" else True


@pytest.fixture(autouse=True)
def require_symlink_permission(request, symlink_capability):
    if "symlink" in request.node.name and symlink_capability is False:
        pytest.skip("Windows token lacks symbolic-link privilege and Developer Mode is disabled")


@pytest.fixture(scope="session")
def bash_executable() -> str:
    """Return a real GNU Bash, avoiding Windows' WSL launcher stub."""
    candidates: list[Path] = []
    override = os.environ.get("AGENT_REACH_TEST_BASH")
    if override:
        candidates.append(Path(override))

    if os.name == "nt":
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            program_files = os.environ.get(env_name)
            if program_files:
                git_root = Path(program_files) / "Git"
                candidates.extend(
                    (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
                )

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            git_root = Path(local_app_data) / "Programs" / "Git"
            candidates.extend(
                (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
            )

        git = shutil.which("git")
        if git:
            git_parent = Path(git).resolve().parent
            if git_parent.name.lower() in {"bin", "cmd"}:
                git_root = git_parent.parent
                candidates.extend(
                    (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
                )

    discovered = shutil.which("bash")
    if discovered:
        candidates.append(Path(discovered))

    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.fspath(candidate))
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        try:
            result = subprocess.run(
                [os.fspath(candidate), "--version"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and "GNU bash" in result.stdout:
            return os.fspath(candidate)

    pytest.fail("GNU Bash is required for shell-script tests")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect every common home/config root before each test runs."""
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.delenv("OPENCLAW_HOME", raising=False)

    config_dir = home / ".agent-reach"
    monkeypatch.setattr(Config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(Config, "CONFIG_FILE", config_dir / "config.yaml")
    return home


@pytest.fixture(autouse=True)
def isolated_xueqiu_cookie_jar(monkeypatch):
    """Prevent the module-level Xueqiu session from leaking between tests."""
    from agent_reach.channels import xueqiu

    xueqiu._cookie_jar.clear()
    monkeypatch.setattr(xueqiu, "_cookies_initialized", False)
    yield
    xueqiu._cookie_jar.clear()
