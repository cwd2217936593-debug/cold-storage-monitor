        THUMB
        AREA    RESET, DATA, READONLY
        EXPORT  __Vectors
__Vectors
        DCD     0x20005000
        DCD     Reset_Handler
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        DCD     0
        AREA    |.text|, CODE, READONLY
        EXPORT  Reset_Handler [WEAK]
Reset_Handler PROC
        IMPORT  SystemInit
        IMPORT  main
        LDR     R0, =SystemInit
        BLX     R0
        LDR     R0, =main
        BX      R0
        ENDP
        END
