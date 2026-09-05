import subprocess, os
from pathlib import Path

path = r"C:\Users\acer\OneDrive\Documents\Aadhisesha\CT20265021581_Application_Form.pdf"
print("File exists:", Path(path).exists())

# Test 1: start via shell=True
print("\nTest 1: subprocess.Popen start shell=True")
try:
    r = subprocess.Popen(f'start "" "{path}"', shell=True)
    print("  OK pid:", r.pid)
except Exception as e:
    print("  FAIL:", e)

import time; time.sleep(2)

# Test 2: os.startfile
print("\nTest 2: os.startfile")
try:
    os.startfile(path)
    print("  OK")
except Exception as e:
    print("  FAIL:", e)

time.sleep(2)

# Test 3: explorer /select
print("\nTest 3: explorer /select")
try:
    r = subprocess.Popen(f'explorer /select,"{path}"', shell=True)
    print("  OK pid:", r.pid)
except Exception as e:
    print("  FAIL:", e)

time.sleep(2)

# Test 4: cmd /c start
print("\nTest 4: cmd /c start")
try:
    r = subprocess.Popen(["cmd", "/c", "start", "", path])
    print("  OK pid:", r.pid)
except Exception as e:
    print("  FAIL:", e)
