@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title ConflictCompass - AI 辅助 HR 沟通话术工具

echo ========================================
echo   ConflictCompass - AI 辅助 HR 沟通话术
echo ========================================
echo.

:: 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址：https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/3] 检测到 Python 环境...

:: 检查并设置 API Key
if "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo [提醒] 未检测到 ANTHROPIC_API_KEY 环境变量
    echo.
    set /p API_KEY="请输入你的 Claude API Key（输入后回车，若无请访问 console.anthropic.com 获取）："
    set ANTHROPIC_API_KEY=!API_KEY!
    echo.
)

:: 安装依赖
echo [2/3] 正在检查/安装项目依赖...
pip install -r requirements.txt -q --disable-pip-version-check
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败，请检查网络连接后重试
    pause
    exit /b 1
)

:: 启动服务
echo [3/3] 启动 ConflictCompass 服务...
echo.
:: 获取本机局域网 IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set LAN_IP=%%a
    set LAN_IP=!LAN_IP: =!
)

echo.
start "" http://127.0.0.1:5000
echo ========================================
echo   服务已启动，浏览器中将打开页面：
echo   本机访问: http://127.0.0.1:5000
if not "!LAN_IP!"=="" (
    echo   局域网访问: http://!LAN_IP!:5000
    echo.
    echo   [提示] 将此链接发给同事即可访问：
    echo   http://!LAN_IP!:5000
    echo   （双方需在同一WiFi/办公网络下）
) else (
    echo.
    echo   [注意] 无法获取本机IP，请手动查看网络设置
)
echo.
echo   如他人无法访问，请检查Windows防火墙
echo   是否允许了5000端口的入站连接
echo   按 Ctrl+C 可停止服务
echo ========================================

python server.py
pause
