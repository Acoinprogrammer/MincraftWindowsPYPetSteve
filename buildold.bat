@echo off
chcp 65001 >nul
cd /d %~dp0
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist StevePet.spec del /q StevePet.spec

set "PYI=%~dp0..\Scripts\pyinstaller.exe"
if not exist "%PYI%" (
    echo [ERROR] 没找到 %PYI%
    pause
    exit /b 1
)

"%PYI%" -F -w --name "StevePet" ^
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
  --add-data "点击身体叫声.mp4;." ^
  --add-data "愤怒音效.mp4;." ^
  --runtime-hook "preload_llama.py" ^
  --hidden-import llama_cpp ^
  --collect-binaries llama_cpp ^
  T12.py

pause