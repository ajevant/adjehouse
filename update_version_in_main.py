#!/usr/bin/env python3
"""Update VERSION in adjehouse_main.py before building"""

import re
import sys

def update_version(version_number):
    """Update VERSION in adjehouse_main.py"""
    try:
        with open('adjehouse_main.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace VERSION = "BUILD-XXX" with new version
        new_version = f'BUILD-{version_number}'
        pattern = r'VERSION = "BUILD-\d+"'
        replacement = f'VERSION = "{new_version}"'
        
        new_content = re.sub(pattern, replacement, content)
        
        with open('adjehouse_main.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"Updated VERSION to {new_version} in adjehouse_main.py")
        return True
    except Exception as e:
        print(f"Error updating version: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update_version_in_main.py <version_number>")
        sys.exit(1)
    
    version_number = sys.argv[1]
    if update_version(version_number):
        sys.exit(0)
    else:
        sys.exit(1)

