# Инструкция по установке и запуску Warehouse Manager

## Вариант 1. Запуск готового EXE (One-file / Portable)

1. Перейдите в папку с собранным файлом `WarehouseManager.exe` (в папке `dist/` или в распакованном архиве).
2. Убедитесь, что рядом с `WarehouseManager.exe` находится файл `portable.txt` (для хранения данных в той же папке).
3. Дважды кликните по `WarehouseManager.exe`.
4. При первом запуске в окне авторизации введите:
   - **Логин**: `admin`
   - **Пароль**: `admin123`
5. При необходимости смените пароль администратора в разделе «Настройки» -> «Управление пользователями».

---

## Вариант 2. Запуск из исходного кода Python

### Требования к системе:
- Операционная система: Windows 10 / 11 (или Windows Server 2019+)
- Python 3.10, 3.11, 3.12 или 3.13

### Шаги установки:
1. Откройте командную строку (cmd или PowerShell) в папке проекта `WarehouseManager`.
2. Создайте и активируйте виртуальное окружение:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Установите зависимости:
   ```powershell
   pip install PySide6 SQLAlchemy openpyxl pandas pyinstaller pytest
   ```
4. Запустите приложение:
   ```powershell
   python main.py
   ```
