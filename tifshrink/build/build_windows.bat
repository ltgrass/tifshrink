@echo off
REM Windows 打包: 影像压缩工具.exe + tifshrink-cli.exe
REM 用法(在仓库根目录):  tifshrink\build\build_windows.bat
REM 前置: pip install -r tifshrink\build\requirements-build.txt
REM 注意: 本脚本不删除任何文件 (PyInstaller 用 --noconfirm 覆盖自己的输出)。
setlocal

set HERE=%~dp0
pushd "%HERE%\..\.."
if not exist "tifshrink\gui.py" (
    echo [错误] 请在仓库根目录执行本脚本
    exit /b 2
)

echo == 构建 (onefile) ==
pyinstaller --noconfirm --workpath "dist\_work" "%HERE%tifshrink-windows.spec"
if errorlevel 1 (
    echo [失败] 打包出错, 见上面的日志
    exit /b 1
)

echo.
echo 完成:
echo   dist\影像压缩工具.exe
echo   dist\tifshrink-cli.exe
echo.
echo 自检(建议): dist\tifshrink-cli.exe "某影像.tif" --target 0.5 --json
popd
endlocal
