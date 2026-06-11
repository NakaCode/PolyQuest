@echo off
echo Gerando executavel PolyQuest...
pyinstaller PolyQuest.spec --noconfirm
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Build falhou. Verifique o erro acima.
    pause
    exit /b 1
)
copy /y config.json dist\config.json >nul
echo.
echo Concluido! Executavel gerado em: dist\PolyQuest.exe
echo.
echo Para gerar o instalador, execute o Inno Setup com PolyQuest.iss
pause
