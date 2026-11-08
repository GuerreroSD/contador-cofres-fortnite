@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onedir --windowed --name ContadorCofres --paths . ^
  --hidden-import vigilar_fortnite --hidden-import contador_cofres ^
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  --exclude-module setuptools --exclude-module pkg_resources --exclude-module distutils ^
  --exclude-module pydoc --exclude-module unittest ^
  --workpath build\work --specpath build --distpath build\dist app.py
if errorlevel 1 (pause & exit /b 1)
robocopy build\dist\ContadorCofres ContadorCofres /E /NFL /NDL /NJH /NJS >nul
echo Listo: ContadorCofres\ContadorCofres.exe
pause
