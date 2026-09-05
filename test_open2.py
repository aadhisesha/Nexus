import ctypes, os
from pathlib import Path

path = r"C:\Users\acer\OneDrive\Documents\Aadhisesha\CT20265021581_Application_Form.pdf"
print("File exists:", Path(path).exists())

# Test ShellExecuteW directly
print("\nTest: ShellExecuteW 'open'")
try:
    result = ctypes.windll.shell32.ShellExecuteW(None, "open", path, None, None, 1)
    print("  result:", result, "(>32 = success)")
except Exception as e:
    print("  FAIL:", e)

import time; time.sleep(3)

# Test ShellExecuteW explorer /select
print("\nTest: ShellExecuteW explorer /select")
try:
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "open", "explorer.exe", f'/select,"{path}"', None, 1
    )
    print("  result:", result, "(>32 = success)")
except Exception as e:
    print("  FAIL:", e)
