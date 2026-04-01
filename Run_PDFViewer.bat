@echo off
cd /d "%~dp0"

:: Find the first PDF in the pdf_input folder
set "PDF_FILE="
for %%f in (pdf_input\*.pdf) do (
    set "PDF_FILE=%%f"
    goto :found
)

:found
if defined PDF_FILE (
    echo Opening: %PDF_FILE%
    venv\Scripts\python main.py "%PDF_FILE%"
) else (
    echo No PDF found in pdf_input folder. Opening viewer empty.
    venv\Scripts\python main.py
)

echo.
echo ======================================
echo Program exited. Any errors are above.
echo ======================================
pause
