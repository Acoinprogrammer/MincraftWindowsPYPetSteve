@echo off
chcp 65001 >nul
cd /d %~dp0

REM ============================================
REM  史蒂夫桌宠打包脚本 build.bat
REM  要求：本文件与 T13.py、全部资源文件同目录
REM ============================================

echo [1/5] 激活虚拟环境...
call E:\PYSIDE6\.venv\Scripts\activate.bat
if errorlevel 1 (
    echo [错误] 虚拟环境激活失败，请检查路径 E:\PYSIDE6\.venv\Scripts\activate.bat
    pause
    exit /b 1
)

echo [2/5] 检查 pyinstaller...
where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [错误] 找不到 pyinstaller，请确认已在虚拟环境中安装：
    echo         pip install pyinstaller
    pause
    exit /b 1
)

echo [3/5] 清理旧产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist StevePet.spec del /q StevePet.spec

echo [4/5] 开始打包...
pyinstaller -F -w --name "StevePet" ^
  --add-data "待机动画.gif;." ^
  --add-data "入场动画.gif;." ^
  --add-data "退出动画.gif;." ^
  --add-data "点击左臂动画.gif;." ^
  --add-data "点击右臂动画.gif;." ^
  --add-data "点击左腿动画.gif;." ^
  --add-data "点击右腿动画.gif;." ^
  --add-data "点击身体动画.gif;." ^
  --add-data "长按动画.gif;." ^
  --add-data "愤怒动画.gif;." ^
  --add-data "思考动画.gif;." ^
  --add-data "回答动画.gif;." ^
  --add-data "桌宠动画开头.mp4;." ^
  --add-data "点击身体叫声.MP4;." ^
  --add-data "愤怒音效.mp4;." ^
  --hidden-import llama_cpp ^
  --collect-binaries llama_cpp ^
  T13.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请查看上方 PyInstaller 输出。
    pause
    exit /b 1
)

echo [5/5] 打包完成！
echo.
echo   exe 位置: %~dp0dist\StevePet.exe
echo   首次运行会在 exe 同目录生成 persona.txt（可改人设与开头动画开关）
echo.
pause

