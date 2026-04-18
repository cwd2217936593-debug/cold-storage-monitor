@echo off
setlocal

echo [BUILD] STM32F103 PA0 LED

set KEIL=D:\app\keil5MDK\ARM
set CC=%KEIL%\ARMCC\Bin\armcc.exe
set ASM=%KEIL%\ARMCC\Bin\armasm.exe
set LINK=%KEIL%\ARMCC\Bin\armlink.exe
set ELF=%KEIL%\ARMCC\Bin\fromelf.exe

set PROJ=C:\Users\22179\.qclaw\workspace-agent-a69f0ee3\stm32f1_led_pa0
set SRC=%PROJ%\src
set OUT=%PROJ%\out
set INC=%KEIL%\ARMCC\include

if not exist %OUT% mkdir %OUT%

echo [1/3] Compiling...
%CC% --cpu Cortex-M3 -O1 --apcs=interwork -I %INC% -c -o %OUT%\main.o %SRC%\main.c
if errorlevel 1 goto fail

%CC% --cpu Cortex-M3 -O1 --apcs=interwork -I %INC% -c -o %OUT%\system.o %SRC%\system_stm32f1xx.c
if errorlevel 1 goto fail

echo [2/3] Assembling...
%ASM% --cpu Cortex-M3 -o %OUT%\startup.o %SRC%\startup_stm32f103xb.s
if errorlevel 1 goto fail

echo [3/3] Linking...
%LINK% --cpu Cortex-M3 --entry Reset_Handler --ro-base 0x08000000 --rw-base 0x20000000 --first startup.o(RESET) -o %OUT%\led.axf %OUT%\startup.o %OUT%\main.o %OUT%\system.o
if errorlevel 1 goto fail

echo [OK] Generating binary...
%ELF% --bin %OUT%\led.axf --output %OUT%\led.bin
if errorlevel 1 goto fail

echo [SUCCESS]
dir %OUT%\led.*
goto :end

:fail
echo [FAIL]
exit /b 1

:end
endlocal
