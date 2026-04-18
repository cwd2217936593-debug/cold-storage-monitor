/* STM32F103C8T6 - DHT11 + USART1 + PB12 LED, HSI 8MHz, C89 */
#include <stdint.h>

/* ---------- Registers (all macros) ---------- */
#define RCC_APB2ENR  (*(volatile uint32_t *)0x40021018)
#define GPIOA_CRL    (*(volatile uint32_t *)0x40010800)
#define GPIOA_CRH    (*(volatile uint32_t *)0x40010804)
#define GPIOA_ODR    (*(volatile uint32_t *)0x4001080C)
#define GPIOA_IDR    (*(volatile uint32_t *)0x40010808)
#define GPIOB_CRH    (*(volatile uint32_t *)0x40010C04)
#define GPIOB_ODR    (*(volatile uint32_t *)0x40010C0C)

#define USART1_SR    (*(volatile uint32_t *)0x40013800)
#define USART1_DR    (*(volatile uint32_t *)0x40013804)
#define USART1_BRR   (*(volatile uint32_t *)0x40013808)
#define USART1_CR1   (*(volatile uint32_t *)0x4001380C)

#define SYSTICK_LOAD (*(volatile uint32_t *)0xE000E014)
#define SYSTICK_VAL  (*(volatile uint32_t *)0xE000E018)
#define SYSTICK_CTRL (*(volatile uint32_t *)0xE000E010)

/* ========== delay (8MHz HSI) ========== */
static void delay_ms(uint32_t ms) {
    SYSTICK_CTRL = 0;
    SYSTICK_LOAD = 8000U * ms;   /* 8MHz/8 = 1MHz, 1us per tick */
    SYSTICK_VAL  = 0;
    SYSTICK_CTRL = 1;
    while (!(SYSTICK_CTRL & (1U << 16)));
    SYSTICK_CTRL = 0;
}

static void delay_us(uint32_t us) {
    volatile uint32_t count = us * 2;  /* rough: 2 cycles per iteration @ 8MHz */
    while (count--) { /* spin */ }
}

/* ========== USART1 ========== */
static void uart_init(void) {
    /* AFIO + GPIOA + USART1 */
    RCC_APB2ENR |= (1U << 0) | (1U << 2) | (1U << 14);

    /* PA9 TX: AF push-pull 50MHz (0xB), PA10 RX: floating input (0x4) */
    GPIOA_CRH = (GPIOA_CRH & ~(0xFFU << 4)) | (0x4BU << 4);

    /* 9600 baud @ 8MHz: USARTDIV = 8000000/(16*9600) = 52.083
       mantissa=52, frac=1, BRR = (52<<4)|1 = 0x341 */
    USART1_BRR = 0x341U;

    /* UE + TE + RE, 8N1 */
    USART1_CR1 = (1U << 13) | (1U << 3) | (1U << 2);
}

static void uart_putc(char c) {
    while (!(USART1_SR & (1U << 7)));
    USART1_DR = (uint32_t)c;
}

static void uart_puts(const char *s) {
    while (*s) uart_putc(*s++);
}

/* ========== DHT11 (PA0) ========== */
#define DHT11_PIN  0

static void dht11_set_output(void) {
    GPIOA_CRL = (GPIOA_CRL & ~(0xFU << (DHT11_PIN * 4))) | (0x3U << (DHT11_PIN * 4));
}

static void dht11_set_input(void) {
    GPIOA_CRL = (GPIOA_CRL & ~(0xFU << (DHT11_PIN * 4))) | (0x4U << (DHT11_PIN * 4));
}

static void dht11_write_pin(uint8_t val) {
    if (val)
        GPIOA_ODR |= (1U << DHT11_PIN);
    else
        GPIOA_ODR &= ~(1U << DHT11_PIN);
}

static uint8_t dht11_read_pin(void) {
    return (GPIOA_IDR >> DHT11_PIN) & 1;
}

static uint8_t dht11_read(uint8_t *temp, uint8_t *humi) {
    uint8_t data[5] = {0};
    uint8_t i, j;
    uint32_t timeout;

    dht11_set_output();
    dht11_write_pin(0);
    delay_ms(20);
    dht11_write_pin(1);
    delay_us(30);

    dht11_set_input();
    timeout = 100;
    while (dht11_read_pin() && timeout--) delay_us(1);
    if (!timeout) return 1;

    timeout = 100;
    while (!dht11_read_pin() && timeout--) delay_us(1);
    if (!timeout) return 2;

    timeout = 100;
    while (dht11_read_pin() && timeout--) delay_us(1);
    if (!timeout) return 3;

    for (i = 0; i < 5; i++) {
        for (j = 0; j < 8; j++) {
            timeout = 100;
            while (!dht11_read_pin() && timeout--) delay_us(1);
            delay_us(30);
            data[i] <<= 1;
            if (dht11_read_pin()) {
                data[i] |= 1;
                timeout = 100;
                while (dht11_read_pin() && timeout--) delay_us(1);
            }
        }
    }

    if (data[4] != (uint8_t)(data[0] + data[1] + data[2] + data[3]))
        return 4;

    *humi = data[0];
    *temp = data[2];
    return 0;
}

/* ========== PB12 LED ========== */
static void led_init(void) {
    RCC_APB2ENR |= (1U << 3);
    GPIOB_CRH = (GPIOB_CRH & ~(0xFU << 16)) | (0x3U << 16);
}

static void led_toggle(void) {
    GPIOB_ODR ^= (1U << 12);
}

/* ========== main ========== */
int main(void) {
    uint8_t temp, humi, err;
    char buf[32];
    int idx;

    uart_init();
    led_init();
    uart_puts("STM32 DHT11 Ready\r\n");

    while (1) {
        led_toggle();

        temp = 0;
        humi = 0;
        err = dht11_read(&temp, &humi);

        if (err == 0) {
            idx = 0;
            buf[idx++] = 'T'; buf[idx++] = ':';
            buf[idx++] = '0' + temp / 10;
            buf[idx++] = '0' + temp % 10;
            buf[idx++] = 'C'; buf[idx++] = ' ';
            buf[idx++] = 'H'; buf[idx++] = ':';
            buf[idx++] = '0' + humi / 10;
            buf[idx++] = '0' + humi % 10;
            buf[idx++] = '%';
            buf[idx++] = '\r'; buf[idx++] = '\n';
            buf[idx] = '\0';
            uart_puts(buf);
        } else {
            uart_puts("DHT11 err\r\n");
        }

        delay_ms(2000);
    }
}
