@echo off

REM 检查是否安装了Java
java -version > nul 2>&1
if %errorlevel% neq 0 (
    echo Java 未安装，请先安装Java环境。
    pause
    exit /b 1
)

REM 启动工具
java -jar libs\HOScrcpy.jar -cp Main
pause