#!/usr/bin/env python3
"""
Auto-Update System for ADJEHOUSE
=================================
Checks for updates on startup and handles automatic updates
"""

import os
import sys
import requests
import subprocess
import shutil
import time
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List

# Try to import psutil for process checking
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Update configuration
# GitHub repository URLs for auto-update
VERSION_URL = "https://raw.githubusercontent.com/ajevant/adjehouse/main/version.txt"
VERSION_API_URL = "https://api.github.com/repos/ajevant/adjehouse/contents/version.txt"
DOWNLOAD_URL = "https://raw.githubusercontent.com/ajevant/adjehouse/main/adjehouse.exe"

# Local version file - use executable directory if running as exe, otherwise script directory
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    BASE_DIR = Path(sys.executable).parent
    CURRENT_EXE = Path(sys.executable)
else:
    # Running as script
    BASE_DIR = Path(__file__).parent
    CURRENT_EXE = BASE_DIR / "dist" / "ADJEHOUSE.exe"

VERSION_FILE = BASE_DIR / "version.txt"
# Use temp directory for update.bat so it gets cleaned up automatically
UPDATE_BAT = Path(tempfile.gettempdir()) / "adjehouse_update.bat"

def get_current_version_number() -> Optional[int]:
    """Extract current version number from executable name or version.txt"""
    # Try to extract from executable name first
    if getattr(sys, 'frozen', False):
        exe_name = Path(sys.executable).name
        import re
        match = re.search(r'v(\d+)', exe_name, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    # Try to read from version.txt
    if VERSION_FILE.exists():
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                import re
                match = re.search(r'(\d+)', version)
                if match:
                    return int(match.group(1))
        except Exception:
            pass
    
    return None

def cleanup_old_versions() -> List[str]:
    """
    Remove all old versions of ADJEHOUSE_v*.exe that are older than the current version.
    Returns list of removed version numbers.
    """
    removed_versions = []
    
    if not getattr(sys, 'frozen', False):
        # Not running as executable, skip cleanup
        return removed_versions
    
    try:
        current_version = get_current_version_number()
        if not current_version:
            return removed_versions
        
        exe_dir = Path(sys.executable).parent
        current_exe_name = Path(sys.executable).name
        
        # Find all ADJEHOUSE_v*.exe files
        import re
        pattern = re.compile(r'ADJEHOUSE_v(\d+)\.exe$', re.IGNORECASE)
        
        for exe_file in exe_dir.glob("ADJEHOUSE_v*.exe"):
            # Skip current executable
            if exe_file.name == current_exe_name:
                continue
            
            match = pattern.match(exe_file.name)
            if match:
                version_num = int(match.group(1))
                # Only remove versions older than current
                if version_num < current_version:
                    try:
                        exe_file.unlink()
                        removed_versions.append(f"v{version_num}")
                        # Silently remove old version
                    except Exception as e:
                        # File might be in use, skip it
                        pass
        
    except Exception as e:
        # Silently fail cleanup
        pass
    
    return removed_versions

def get_local_version() -> Optional[str]:
    """Get the local version from executable name only (not version.txt)"""
    # If running as executable, extract version from filename
    if getattr(sys, 'frozen', False):
        exe_name = Path(sys.executable).name
        import re
        match = re.search(r'v(\d+)', exe_name, re.IGNORECASE)
        if match:
            return f"BUILD-{match.group(1)}"
    
    # If running as script, try to find the latest executable in dist directory
    dist_dir = BASE_DIR / "dist"
    if dist_dir.exists():
        exe_files = list(dist_dir.glob("ADJEHOUSE_v*.exe"))
        if exe_files:
            # Get the latest version by extracting version numbers
            import re
            versions = []
            for exe_file in exe_files:
                match = re.search(r'v(\d+)', exe_file.name, re.IGNORECASE)
                if match:
                    versions.append((int(match.group(1)), exe_file))
            
            if versions:
                # Return the highest version
                latest_version = max(versions, key=lambda x: x[0])
                return f"BUILD-{latest_version[0]}"
    
    return None

def get_remote_version() -> Optional[str]:
    """Get the remote version from GitHub by checking the latest commit that updated adjehouse.exe"""
    import json
    import re
    
    # Use GitHub API to get all recent commits to find the highest version
    try:
        # Get the latest commits (all commits, not just adjehouse.exe)
        commits_url = "https://api.github.com/repos/ajevant/adjehouse/commits"
        params = {
            'per_page': 30  # Get more commits to find the highest version
        }
        response = requests.get(commits_url, params=params, timeout=10)
        
        if response.status_code == 200:
            commits = response.json()
            if commits and len(commits) > 0:
                # Extract all versions from commits and find the highest
                versions_found = []
                patterns = [
                    r'Auto-update:\s*Build\s+(\d+)',  # "Auto-update: Build 133"
                    r'Build\s+(\d+)',  # "Build 128" or "Build 128: ..."
                    r'v(\d+)',  # "v128"
                ]
                
                for commit in commits:
                    commit_message = commit.get('commit', {}).get('message', '')
                    
                    for pattern in patterns:
                        match = re.search(pattern, commit_message, re.IGNORECASE)
                        if match:
                            version_num = int(match.group(1))
                            versions_found.append((version_num, commit_message[:50]))
                            break  # Found a version in this commit, move to next
                
                if versions_found:
                    # Get the highest version number
                    highest_version = max(versions_found, key=lambda x: x[0])
                    version = f"BUILD-{highest_version[0]}"
                    return version
    except Exception as e:
        # Silently fail and fall back to other methods
        pass
    
    # Fallback: Try to get version from version.txt (for backwards compatibility)
    try:
        import base64
        response = requests.get(VERSION_API_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'content' in data:
                content = base64.b64decode(data['content']).decode('utf-8')
                version = content.strip().replace('\n', '').replace('\r', '')
                if version:
                    return version
    except Exception:
        pass
    
    # Final fallback: Try raw URL with cache-busting
    try:
        import time
        cache_buster = int(time.time())
        url = f"{VERSION_URL}?t={cache_buster}"
        response = requests.get(url, timeout=10, headers={'Cache-Control': 'no-cache'})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        version = response.text.strip()
        if version:
            return version
    except requests.exceptions.RequestException:
        pass
    
    return None

def compare_versions(local: str, remote: str) -> bool:
    """Compare two version strings. Returns True if remote is newer."""
    if not local or not remote:
        return False
    
    # Handle BUILD-XXX format
    import re
    local_match = re.search(r'(\d+)', local)
    remote_match = re.search(r'(\d+)', remote)
    
    if local_match and remote_match:
        local_num = int(local_match.group(1))
        remote_num = int(remote_match.group(1))
        return remote_num > local_num
    
    # Fallback: simple string comparison
    return remote > local

def save_local_version(version: str):
    """Save the local version to version.txt"""
    try:
        with open(VERSION_FILE, 'w', encoding='utf-8') as f:
            f.write(version)
    except Exception as e:
        pass

def format_bytes(bytes_size: int) -> str:
    """Format bytes to MB"""
    return f"{bytes_size / (1024 * 1024):.1f}"

def download_update(remote_version: str) -> Tuple[bool, Optional[Path], Optional[Path], Optional[Path]]:
    """Download the new version from GitHub and create a new versioned exe file"""
    try:
        # Get the current executable path
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            current_exe = Path(sys.executable)
            exe_dir = current_exe.parent
        else:
            # Running as script
            exe_dir = Path(__file__).parent / "dist"
            current_exe = exe_dir / "ADJEHOUSE.exe"
            if not current_exe.exists():
                # Try to find the latest version
                exe_files = list(exe_dir.glob("ADJEHOUSE*.exe"))
                if exe_files:
                    current_exe = max(exe_files, key=lambda p: p.stat().st_mtime)
        
        # Extract version number from remote_version (e.g., "BUILD-122" -> "122")
        import re
        version_match = re.search(r'(\d+)', remote_version)
        if not version_match:
            print("[UPDATE] Error: Could not parse version number from remote version")
            return False, None, None, None
        
        version_num = version_match.group(1)
        
        # Create new versioned exe path (in same directory as current exe)
        new_exe_path = exe_dir / f"ADJEHOUSE_v{version_num}.exe"
        
        # Check if new version already exists
        if new_exe_path.exists():
            # Version already exists - return without message (caller will handle switching)
            return True, None, new_exe_path, current_exe
        
        # Import time module for timing operations
        import time
        
        # Download new version to temporary file in same directory
        temp_path = exe_dir / f"ADJEHOUSE_v{version_num}.exe.tmp"
        
        response = requests.get(DOWNLOAD_URL, timeout=60, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        start_time = time.time()
        last_update = time.time()
        
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Update progress every 0.1 seconds
                    current_time = time.time()
                    if current_time - last_update >= 0.1 or downloaded == total_size:
                        last_update = current_time
                        
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            elapsed = current_time - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            
                            # Enhanced progress bar with better formatting
                            bar_width = 30
                            filled = int(bar_width * percent / 100)
                            bar = '█' * filled + '░' * (bar_width - filled)
                            
                            downloaded_mb = downloaded / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            speed_mb = speed / (1024 * 1024) if speed > 0 else 0
                            
                            # Format: [████████████] 100.0% | 28.1 MB / 28.1 MB | 82.1 MB/s
                            print(f"\r[UPDATE] [{bar}] {percent:.1f}% | {downloaded_mb:.1f} MB / {total_mb:.1f} MB | {speed_mb:.1f} MB/s", end='', flush=True)
        
        print()  # New line after progress
        
        # Ensure the file is fully written to disk
        time.sleep(0.5)  # Small delay to ensure file is flushed
        
        # Verify the file exists and has content
        if not temp_path.exists() or temp_path.stat().st_size == 0:
            print("[UPDATE] ERROR: Downloaded file is empty or missing")
            return False, None, None, None
        
        return True, temp_path, new_exe_path, current_exe
        
    except requests.exceptions.RequestException as e:
        print(f"[UPDATE] ERROR: Failed to download update: {e}")
        return False, None, None, None
    except Exception as e:
        print(f"[UPDATE] ERROR: Download failed: {e}")
        return False, None, None, None

def is_process_running(exe_path: Path) -> bool:
    """Check if a process with the given executable path is currently running"""
    if not PSUTIL_AVAILABLE:
        # Fallback: use tasklist command on Windows
        try:
            exe_name = os.path.basename(exe_path)
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {exe_name}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            # If tasklist finds the process, it will contain the exe name in output
            return exe_name.lower() in result.stdout.lower()
        except Exception:
            # If check fails, assume process might be running (safer)
            return True
    
    try:
        exe_path_abs = os.path.abspath(exe_path)
        exe_name = os.path.basename(exe_path_abs)
        
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['name'] and exe_name.lower() == proc.info['name'].lower():
                    # Check if the executable path matches
                    if proc.info['exe']:
                        proc_exe_abs = os.path.abspath(proc.info['exe'])
                        if proc_exe_abs.lower() == exe_path_abs.lower():
                            return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return False
    except Exception:
        # If psutil fails, assume process might be running (safer)
        return True

def create_update_bat(temp_path: Path, new_exe_path: Path, old_exe_path: Path, remote_version: str, old_exe_running: bool = False):
    """Create a batch file to complete the update after the application closes"""
    import os
    
    # Get absolute paths
    temp_path_abs = os.path.abspath(temp_path) if temp_path else None
    new_exe_path_abs = os.path.abspath(new_exe_path)
    old_exe_path_abs = os.path.abspath(old_exe_path)
    
    # Get just the filenames
    new_exe_name = os.path.basename(new_exe_path_abs)
    old_exe_name = os.path.basename(old_exe_path_abs)
    
    if temp_path_abs:
        # Normal update: move temp file to new exe
        if old_exe_running:
            # Old exe is running, wait for user to close it
            wait_and_remove = f"""
    REM Old version is still running, wait for user to close it
    :wait_loop
    timeout /t 2 /nobreak >nul
    tasklist /FI "IMAGENAME eq {old_exe_name}" 2>NUL | find /I /N "{old_exe_name}">NUL
    if "%ERRORLEVEL%"=="0" goto wait_loop
    
    REM Try to delete old exe
    if exist "{old_exe_path_abs}" (
        del /f /q "{old_exe_path_abs}" >nul 2>&1
    )
"""
        else:
            # Old exe is not running, try to close and remove immediately
            wait_and_remove = f"""
    REM Old version is not running, attempting to close and remove
    taskkill /F /IM "{old_exe_name}" >nul 2>&1
    timeout /t 1 /nobreak >nul
    
    REM Try to delete old exe silently
    if exist "{old_exe_path_abs}" (
        del /f /q "{old_exe_path_abs}" >nul 2>&1
    )
"""
        
        bat_content = f"""@echo off
REM Hide window (CREATE_NO_WINDOW equivalent)
if "%1"=="hidden" goto :hidden
start /min "" "%~f0" hidden %*
exit /b

:hidden
timeout /t 2 /nobreak >nul

REM Check if new version already exists
if exist "{new_exe_path_abs}" (
    goto :start_new
)

REM Check if temp file exists, wait a bit if it doesn't
set "retry_count=0"
:check_temp
if exist "{temp_path_abs}" goto :move_file
set /a retry_count+=1
if %retry_count% geq 10 (
    if not exist "{new_exe_path_abs}" (
        exit /b 1
    )
    goto :start_new
)
timeout /t 1 /nobreak >nul
goto :check_temp

:move_file
REM Move temp file to new versioned exe
move /y "{temp_path_abs}" "{new_exe_path_abs}" >nul 2>&1
if errorlevel 1 (
    exit /b 1
)

:start_new
{wait_and_remove}
REM Start the new version
start "" "{new_exe_path_abs}"

REM Exit immediately - don't try to delete batch file (causes errors)
REM Windows will clean up temp files automatically
exit /b 0
"""
    else:
        # Update already exists, just start it
        bat_content = f"""@echo off
REM Hide window completely
if "%1"=="hidden" goto :hidden
start /min "" "%~f0" hidden %*
exit /b

:hidden
REM Start the new version silently
start "" "{new_exe_path_abs}"

REM Exit immediately - Windows will clean up temp files automatically
exit /b 0
"""
    
    try:
        with open(UPDATE_BAT, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        return True
    except Exception as e:
        print(f"[UPDATE] Error creating update script: {e}")
        return False

def check_for_updates(skip_prompt: bool = False, current_version: Optional[str] = None) -> bool:
    """
    Check for updates and handle the update process.
    Returns True if update was performed (and app should exit), False otherwise.
    
    Args:
        skip_prompt: If True, skip user prompt and auto-update
        current_version: Optional version string to use instead of reading from file
    """
    try:
        # CRITICAL: Early exit check - if running as executable, check filename first
        # This prevents any unnecessary remote checks or messages
        if getattr(sys, 'frozen', False):
            cleanup_old_versions()
            
            # Extract current version from executable filename immediately
            exe_name = Path(sys.executable).name
            import re
            current_match = re.search(r'v(\d+)', exe_name, re.IGNORECASE)
            if current_match:
                current_exe_version = int(current_match.group(1))
                exe_dir = Path(sys.executable).parent
                
                # Check if there's a newer local version first (before any remote checks)
                exe_files = list(exe_dir.glob("ADJEHOUSE_v*.exe"))
                if exe_files:
                    local_versions = []
                    for exe_file in exe_files:
                        match = re.search(r'v(\d+)', exe_file.name, re.IGNORECASE)
                        if match:
                            local_versions.append(int(match.group(1)))
                    
                    if local_versions:
                        highest_local = max(local_versions)
                        # If we're already running the highest local version, 
                        # do a quick remote check but exit immediately if we're already up to date
                        if current_exe_version >= highest_local:
                            # We're running highest local, check remote quickly
                            remote_version = get_remote_version()
                            if remote_version:
                                remote_match = re.search(r'(\d+)', remote_version)
                                if remote_match:
                                    remote_num = int(remote_match.group(1))
                                    if current_exe_version >= remote_num:
                                        # Already on latest - exit silently IMMEDIATELY
                                        return False
        
        # Get local version first (silent)
        local_version = current_version or get_local_version()
        if not local_version:
            # No local version found - silently continue
            return False
        
        # Early check: If running as executable, check if we're already running the highest local version
        # This avoids unnecessary remote version checks
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            current_exe_name = Path(sys.executable).name
            
            # Extract our current version number from executable name
            import re
            current_match = re.search(r'v(\d+)', current_exe_name, re.IGNORECASE)
            if current_match:
                current_version_num = int(current_match.group(1))
                
                # Check all local executable versions to see if we're running the highest
                exe_files = list(exe_dir.glob("ADJEHOUSE_v*.exe"))
                if exe_files:
                    local_versions = []
                    for exe_file in exe_files:
                        match = re.search(r'v(\d+)', exe_file.name, re.IGNORECASE)
                        if match:
                            local_versions.append(int(match.group(1)))
                    
                    if local_versions:
                        highest_local = max(local_versions)
                        # If we're running the highest local version, check remote version
                        # If we're NOT running the highest local, we should switch to it first
                        if current_version_num < highest_local:
                            # A newer local version exists - switch to it silently
                            new_exe_path = exe_dir / f"ADJEHOUSE_v{highest_local}.exe"
                            if new_exe_path.exists():
                                old_exe_running = is_process_running(Path(sys.executable))
                                # Create fake remote_version for switching
                                fake_remote_version = f"BUILD-{highest_local}"
                                if create_update_bat(None, new_exe_path, Path(sys.executable), fake_remote_version, old_exe_running):
                                    import time
                                    time.sleep(1)
                                    subprocess.Popen([str(UPDATE_BAT)], shell=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                                    return True
                            return False
        
        # Get remote version (silent)
        remote_version = get_remote_version()
        
        if not remote_version:
            # No remote version found - silently continue
            return False
        
        # Extract version numbers for comparison
        import re
        local_match = re.search(r'(\d+)', local_version)
        local_num = int(local_match.group(1)) if local_match else 0
        remote_match = re.search(r'(\d+)', remote_version)
        remote_num = int(remote_match.group(1)) if remote_match else 0
        
        # If versions are equal or local is newer, silently continue
        if local_num >= remote_num:
            # Already running latest or newer version - silently continue
            return False
        
        # Double-check: If we're running as executable, verify by filename
        if getattr(sys, 'frozen', False):
            current_exe_name = Path(sys.executable).name
            if current_exe_name == f"ADJEHOUSE_v{remote_num}.exe":
                # We're already running the latest version - silently continue
                return False
        else:
            exe_dir = BASE_DIR / "dist"
            current_exe = exe_dir / "ADJEHOUSE.exe"
            if not current_exe.exists():
                exe_files = list(exe_dir.glob("ADJEHOUSE*.exe"))
                if exe_files:
                    current_exe = max(exe_files, key=lambda p: p.stat().st_mtime)
        
        new_exe_path = exe_dir / f"ADJEHOUSE_v{remote_num}.exe"
        
        # Compare versions (silent)
        is_newer = compare_versions(local_version, remote_version)
        
        if not is_newer:
            # No update available - silently return False
            return False
        
        # If new version already exists locally, switch to it silently without download messages
        if new_exe_path.exists():
            # New version exists, just switch to it without showing download messages
            old_exe_running = is_process_running(current_exe)
            if not create_update_bat(None, new_exe_path, current_exe, remote_version, old_exe_running):
                return False
            try:
                import time
                time.sleep(1)  # Brief pause before switching
                subprocess.Popen([str(UPDATE_BAT)], shell=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                return True  # Signal that app should exit
            except Exception as e:
                return False
        
        # New version doesn't exist locally - need to download it
        # Update available - auto-install
        print(f"\n[UPDATE] ⚠️  New version available! (v{local_num} → v{remote_num})")
        print("[UPDATE] Downloading update...")
        
        if not skip_prompt:
            # Give user 2 seconds to cancel with Ctrl+C
            import time
            try:
                time.sleep(2)
            except KeyboardInterrupt:
                print("\n[UPDATE] Update cancelled by user")
                return False
        
        # Download update (pass remote_version so it can determine new exe name)
        try:
            success, temp_path, new_exe_path, old_exe_path = download_update(remote_version)
            if not success or not new_exe_path or not old_exe_path:
                print("[UPDATE] ERROR: Failed to download update")
                return False
        except Exception as e:
            print(f"[UPDATE] ERROR: Failed to download update: {e}")
            return False
        
        # Check if old exe is still running
        old_exe_running = is_process_running(old_exe_path)
        
        # Countdown before closing (silent)
        import time
        time.sleep(2)  # Wait 2 seconds before closing
        
        # Create update batch file
        if not create_update_bat(temp_path, new_exe_path, old_exe_path, remote_version, old_exe_running):
            print("[UPDATE] Failed to create update script.")
            return False
        
        # Launch update batch file
        try:
            # Start the update batch file (it will wait for the app to close)
            subprocess.Popen([str(UPDATE_BAT)], shell=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return True  # Signal that app should exit
        except Exception as e:
            print(f"[UPDATE] Error launching update script: {e}")
            return False
            
    except KeyboardInterrupt:
        print("\n[UPDATE] Update cancelled by user")
        return False
    except Exception as e:
        print(f"[UPDATE] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # For testing - silent mode (no output if already on latest version)
    result = check_for_updates(skip_prompt=True)
    # Don't print anything - just exit silently
    sys.exit(0 if not result else 1)
