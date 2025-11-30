#!/usr/bin/env python3
"""Get next version number for ADJEHOUSE executable"""

import os
import re
import glob
from pathlib import Path

# Find all existing ADJEHOUSE_v*.exe files in dist directory
dist_dir = Path("dist")
if not dist_dir.exists():
    print("1")
    exit(0)

exe_files = list(dist_dir.glob("ADJEHOUSE_v*.exe"))

if not exe_files:
    print("1")
    exit(0)

# Extract version numbers
versions = []
for exe_file in exe_files:
    match = re.search(r'_v(\d+)', exe_file.name)
    if match:
        versions.append(int(match.group(1)))

if not versions:
    print("1")
    exit(0)

# Get next version
next_version = max(versions) + 1
print(next_version)







