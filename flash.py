import serial
import time
import sys

SERIAL_PORT = 'COM12'
BAUD = 57600
BIN_FILE = r'C:\Users\22179\.qclaw\workspace-agent-a69f0ee3\stm32f1_led_pa0\out\led.bin'
FLASH_ADDR = 0x08000000

def wait_ack(ser, timeout=3):
    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting:
            data = ser.read(1)
            return data[0] == 0x79
    return False

print('=== STM32 Flash Programming ===')

# Open serial
ser = serial.Serial(SERIAL_PORT, BAUD, timeout=3)
ser.flushInput()

# Sync
print('1. Syncing...')
ser.write(b'\x7F')
time.sleep(0.2)
resp = ser.read(ser.in_waiting) if ser.in_waiting else b''
if b'\x79' not in resp:
    print('  FAILED:', resp.hex())
    ser.close()
    sys.exit(1)
print('  OK')

# Get ID
print('2. Get chip ID...')
ser.write(bytes([0x02, 0xFD]))
time.sleep(0.2)
resp = ser.read(ser.in_waiting) if ser.in_waiting else b''
if len(resp) >= 4:
    chip_id = (resp[2] << 8) | resp[3]
    print(f'  ID: 0x{chip_id:04X}')
else:
    print('  Response:', resp.hex())

# Read firmware
with open(BIN_FILE, 'rb') as f:
    firmware = f.read()
print(f'3. Firmware: {len(firmware)} bytes')

# Erase (Extended Erase 0x44)
print('4. Erasing flash...')
ser.write(bytes([0x44, 0xBB]))
time.sleep(0.2)
if not wait_ack(ser):
    # Try standard erase 0x43
    ser.write(bytes([0x43, 0xBC]))
    time.sleep(0.2)
    if wait_ack(ser):
        # Global erase for 0x43
        ser.write(bytes([0xFF, 0x00]))
        time.sleep(3)
        if wait_ack(ser, timeout=10):
            print('  Erase OK (0x43)')
        else:
            print('  Erase failed')
            ser.close()
            sys.exit(1)
    else:
        print('  Erase command failed')
        ser.close()
        sys.exit(1)
else:
    # Extended erase: global erase = 0xFFFF, 0x00
    ser.write(bytes([0xFF, 0xFF, 0x00]))
    time.sleep(5)
    if wait_ack(ser, timeout=10):
        print('  Erase OK (0x44)')
    else:
        print('  Erase failed')
        ser.close()
        sys.exit(1)

# Write firmware
print('5. Writing firmware...')
offset = 0
addr = FLASH_ADDR
chunk_size = 256

while offset < len(firmware):
    chunk = firmware[offset:offset+chunk_size]
    # Pad to 4-byte boundary
    while len(chunk) % 4:
        chunk += b'\xFF'
    
    # Write command
    ser.write(bytes([0x31, 0xCE]))
    time.sleep(0.1)
    if not wait_ack(ser):
        print(f'  Write cmd failed at {offset}')
        break
    
    # Address
    addr_bytes = [(addr >> 24) & 0xFF, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF]
    ser.write(bytes(addr_bytes))
    checksum = (~sum(addr_bytes)) & 0xFF
    ser.write(bytes([checksum]))
    time.sleep(0.1)
    if not wait_ack(ser):
        print('  Address failed')
        break
    
    # Data
    n = len(chunk) - 1
    data_packet = bytes([n]) + chunk
    checksum = (~sum(data_packet)) & 0xFF
    ser.write(data_packet + bytes([checksum]))
    time.sleep(0.1)
    
    if wait_ack(ser):
        print(f'  0x{addr:08X}: {len(chunk)} bytes')
    else:
        print(f'  Write failed at 0x{addr:08X}')
        break
    
    addr += len(chunk)
    offset += chunk_size

# Go
print('6. Jump to 0x08000000...')
ser.write(bytes([0x21, 0xDE]))
time.sleep(0.1)
if wait_ack(ser):
    addr_bytes = [(FLASH_ADDR >> 24) & 0xFF, (FLASH_ADDR >> 16) & 0xFF, (FLASH_ADDR >> 8) & 0xFF, FLASH_ADDR & 0xFF]
    checksum = (~sum(addr_bytes)) & 0xFF
    ser.write(bytes(addr_bytes) + bytes([checksum]))
    print('  Jump sent!')

ser.close()
print('=== Done ===')
