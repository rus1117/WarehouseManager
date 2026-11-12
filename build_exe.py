"""Скрипт сборки исполняемого файла EXE через PyInstaller."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
DIST_DIR.mkdir(parents=True, exist_ok=True)
TARGET_EXE = DIST_DIR / "WarehouseManager.exe"

# Пытаемся освободить старый файл EXE (в Windows запущенный EXE можно переименовать, даже если нельзя удалить)
if TARGET_EXE.exists():
    try:
        TARGET_EXE.unlink()
    except PermissionError:
        old_bak = DIST_DIR / f"WarehouseManager_old_{os.getpid()}.bak"
        try:
            TARGET_EXE.rename(old_bak)
        except Exception as e:
            print(f"Не удалось переименовать запущенный EXE: {e}")

# Собираем во временную папку и затем перемещаем в dist
tmp_dist = Path(tempfile.mkdtemp(prefix="wm_dist_"))

cmd = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--name=WarehouseManager",
    "--windowed",
    "--onefile",
    f"--distpath={tmp_dist}",
    f"--add-data={ROOT / 'portable.txt'};.",
    str(ROOT / "main.py"),
]

print("Запуск PyInstaller:", " ".join(cmd))
res = subprocess.run(cmd, cwd=str(ROOT))
if res.returncode != 0:
    shutil.rmtree(tmp_dist, ignore_errors=True)
    sys.exit(res.returncode)

built_exe = tmp_dist / "WarehouseManager.exe"
if built_exe.exists():
    try:
        if TARGET_EXE.exists():
            TARGET_EXE.unlink()
        shutil.move(str(built_exe), str(TARGET_EXE))
        print(f"УСПЕХ: Обновлён файл {TARGET_EXE}")
    except PermissionError:
        alt_exe = DIST_DIR / "WarehouseManager_v1.0.exe"
        shutil.copy2(str(built_exe), str(alt_exe))
        print(f"ВНИМАНИЕ: Основной EXE сейчас открыт, сборка сохранена также в {alt_exe}")

# Копируем маркер портативности рядом с EXE
shutil.copy2(str(ROOT / "portable.txt"), str(DIST_DIR / "portable.txt"))
shutil.rmtree(tmp_dist, ignore_errors=True)
