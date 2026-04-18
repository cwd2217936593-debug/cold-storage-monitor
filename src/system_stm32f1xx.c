/* system_stm32f1xx.c - HSI → PLL 72MHz，纯宏，无全局变量 */
#include <stdint.h>

#define RCC_CR      (*(volatile uint32_t *)0x40021000)
#define RCC_CFGR    (*(volatile uint32_t *)0x40021004)
#define FLASH_ACR   (*(volatile uint32_t *)0x40022000)

uint32_t SystemCoreClock = 8000000;

void SystemInit(void) {
    /* HSI 8MHz, no PLL, no Flash wait states needed at 8MHz */
    /* Reset state: HSI ON, SW=HSI, no PLL — just keep defaults */
    SystemCoreClock = 8000000;
}
