@echo off
echo Building PDF Viewer...
cd /d "%~dp0"
venv\Scripts\pyinstaller PDFViewer.spec --noconfirm
echo.
if exist "dist\PDFViewer\PDFViewer.exe" (
    echo Build successful! Output: dist\PDFViewer\
) else (
    echo Build FAILED.
)
pause
