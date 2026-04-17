import os
import shutil
import sys
import site
from pathlib import Path

def harden():
    print("--- Annadata OS: Environment Hardening & Self-Healing ---")
    
    # Get all site-packages directories
    sp_dirs = site.getsitepackages()
    if site.getusersitepackages():
        sp_dirs.append(site.getusersitepackages())
        
    corrupted_found = False
    
    for sp in sp_dirs:
        sp_path = Path(sp)
        if not sp_path.exists():
            continue
            
        print(f"Auditing: {sp_path}")
        
        # Look for directories starting with ~
        for item in sp_path.iterdir():
            if item.is_dir() and item.name.startswith("~"):
                print(f"Found corrupted zombie directory: {item.name}")
                try:
                    shutil.rmtree(item)
                    print(f"Successfully purged: {item.name}")
                    corrupted_found = True
                except Exception as e:
                    print(f"Failed to purge {item.name}: {e}")
                    
    if corrupted_found:
        print("Done. Environment is now clean.")
    else:
        print("No corruption detected. Environment is healthy.")

if __name__ == "__main__":
    harden()
