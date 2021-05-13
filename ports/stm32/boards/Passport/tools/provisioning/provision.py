# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
import telnetlib
import sys
import os
import serial
import re
import time
from binascii import hexlify

from simple_term_menu import TerminalMenu

# - User must run ocd before this app and ensure it connected to the device

HOST = 'localhost'

tn = None

BL_NVROM_BASE = 0x0801FF00
SUPPLY_CHAIN_SECRET_ADDRESS = 0x81E0000
SERIAL_PORT_NAME = '/dev/ttyACM0'

FIRMWARE_PATH = os.path.expanduser('~/provisioning/passport-fw.bin')
BOOTLOADER_PATH = os.path.expanduser('~/provisioning/passport-bl.bin')
SECRETS_PATH = os.path.expanduser('~/provisioning/secrets.bin')
SCV_KEY_PATH = os.path.expanduser('~/provisioning/scv-key.bin')

OCD_CMD_LINE = ['sudo', '/usr/local/bin/openocd', '-f', 'stlink.cfg', '-c', 'adapter speed 1000; transport select hla_swd', '-f', 'stm32h7x.cfg']
ocd_proc = None

TELNET_CMD_LINE = ['telnet', 'localhost', '4444']
telnet_proc = None


# FACTORY SETTINGS
DIAGNOSTIC_MODE = False    # Set to True to get more menu options


def connect_to_telnet():
    # Connect
    global tn
    tn = telnetlib.Telnet(HOST, 4444)
    # Turn off echo so expect doesn't get confused by the commands we send
    # We still see the commands we send echoed from the remote side, but they are not also echoed locally now.
    tn.write(b'' + telnetlib.IAC + telnetlib.DONT + telnetlib.ECHO)


# Numato 32 channel GPIO board over USB serial:
#
# - https://numato.com/product/32-channel-usb-gpio-module-with-analog-inputs/
# - https://github.com/numato/samplecode/blob/master/RelayAndGPIOModules/USBRelayAndGPIOModules/python/usbgpio16_32/gpioread.py
# - https://github.com/numato/samplecode/blob/master/RelayAndGPIOModules/USBRelayAndGPIOModules/python/usbgpio16_32/gpiowrite.py
# - https://github.com/numato/samplecode/blob/master/RelayAndGPIOModules/USBRelayAndGPIOModules/python/usbgpio16_32/analogread.py
def is_set():
    serial_port = serial.Serial(SERIAL_PORT_NAME, 19200, timeout=1)
    print('serial_port={}'.format(serial_port))
    serial_port.write(b"gpio read 0\r")
    response = serial_port.read(25).decode('utf-8')
    print('response = {}'.format(response))
    value = response[-4:-3]

    print('GPIO status = {}'.format(value))
    serial_port.close()
    return value == '1'

def set_gpio(serial_port, gpio_num, set):
    cmd = 'gpio {} {}\r'.format('set' if set else 'clear', gpio_num)
    serial_port.write(bytes(cmd, 'utf-8'))

def power_device(turn_on):
    serial_port = serial.Serial(SERIAL_PORT_NAME, 19200, timeout=1)

    if turn_on:
        # Hold low for at least 0.5s to turn on
        print('Powering on!')
        set_gpio(serial_port, 0, False)  # Low means "active"
        time.sleep(1)
        set_gpio(serial_port, 0, True)   # Back to normal
    else:
        # Hold low for at least 5s to turn off
        set_gpio(serial_port, 0, False)  # Low means "active"
        for i in range(5,-1, -1):
            print('Powering down in {}'.format(i))
            time.sleep(1)

        # One extra sleep to make sure we held it low long enough
        time.sleep(1)
        set_gpio(serial_port, 0, True)   # Back to normal

    serial_port.close()

def wait_for_prompt(timeout=None):
    if timeout == None:
        result = tn.expect([b'>',b'Error'])
    else:
        result = tn.expect([b'>',b'Error'], timeout)

    r = tn.read_very_eager()

    if result[0] == -1 or len(result[2]) == 0 or result[0] == 1:
        return False
    else:
        return True

# Put device into halt state, and discard all unread data to get ready for a new command
def init_device(timeout=None):
    r = tn.read_very_eager()
    # print('Halting device...')
    tn.write(b'reset halt\r')
    return wait_for_prompt(timeout)

def random_fn_ext(l):
    import os, binascii
    return binascii.b2a_hex(os.urandom(l)).decode('utf-8')

def provision_device(flash_bootloader=False, flash_firmware=False, with_secrets=False):
    init_device()

    # Check to see if the device was already provisioned - it will have data in its secrets
    if flash_bootloader and not with_secrets:
        secrets_text = get_secrets()
        secrets = parse_secrets(secrets_text)
        if is_already_provisioned(secrets):
            print('This device is already provisioned! Provisioning it again will erase the secrets and render the device inoperable.\n\nProvisioning canceled.')
            return

        write_supply_chain_secret()

    if flash_firmware:
        # Program the Firmware
        print('Programming the Firmware...')
        cmd = 'flash write_image erase {} 0x8020000\r'.format(FIRMWARE_PATH)
        tn.write(bytes(cmd, 'utf-8'))
        result = wait_for_prompt()

    if flash_bootloader:
        # Program the Bootloader
        if with_secrets:
            from shutil import copyfile
            # Create a temporary file and write the firmware to it with
            dst_path = os.path.expanduser('~/provisioning/tmp-passport-bl-{}.bin'.format(random_fn_ext(4)))
            copyfile(BOOTLOADER_PATH, dst_path)

            # Read in secrets and append to file
            if os.path.isfile(SECRETS_PATH):
                src_fd = open(SECRETS_PATH, 'rb')
                dst_fd = open(dst_path, 'ab')
                dst_fd.write(src_fd.read())
                dst_fd.close()  # Have to close this immediately or the additional secrets bytes won't be flashed!
                print('Creating temporary file for writing bootloader with secrets: {}'.format(dst_path))
            else:
                print('Error: No secrets.bin file exists')
                return
        else:
            dst_path = BOOTLOADER_PATH

        print('Programming the Bootloader...')
        cmd = 'flash write_image erase {} 0x8000000\r'.format(dst_path)
        print('cmd: {}'.format(cmd))
        tn.write(bytes(cmd, 'utf-8'))
        wait_for_prompt()

        if with_secrets:
            # Delete the temporary file
            os.remove(dst_path)
            pass

    # Reset device for first boot
    print('Resetting device and waiting for initial provisioning to complete...')
    tn.write(b'reset\r')
    wait_for_prompt()

    # Provisioning should only take about 5 seconds, but boot takes 3-4 seconds
    if not flash_bootloader or with_secrets:
        print('Waiting for device to restart...')
    else:
        print('Device provisioning in progress...')
    for i in range(10, -1, -1):
        print('  {}...'.format(i))
        time.sleep(1)

    print('Complete!')

def write_supply_chain_secret():
    init_device()

    # Write the supply chain secret
    print('Setting Supply Chain Validation Secret...')
    size = os.path.getsize(SCV_KEY_PATH)
    if size != 32:
        print('ERROR: scv-key.bin must be exactly 32 bytes long')
        sys.exit(1)

    cmd = 'flash write_image erase {} {}\r'.format(SCV_KEY_PATH, hex(SUPPLY_CHAIN_SECRET_ADDRESS))
    tn.write(bytes(cmd, 'utf-8'))
    wait_for_prompt()

def test_device_connection():
    tn.read_very_eager()
    device_found = init_device(timeout=5)
    if device_found:
        print('Passport is connected and responding to commands.')
    else:
        print('===================================================================')
        print('Unable to connect to device (Error or timeout connecting to device)')
        print('===================================================================')

def read_supply_chain_secret(do_init=True):
    if do_init:
        init_device()

    # Read the supply chain secret to make sure the device is ready for provisioning
    tn.write(bytes('mdb {} 32\r'.format(hex(SUPPLY_CHAIN_SECRET_ADDRESS)), 'utf-8'))
    result = tn.expect([b'>'])[2].decode('utf-8')
    lines = result.split('\r\n')[1:]
    lines = lines[:-2]
    lines = '\n'.join(lines)
    print('\nSupply Chain Secret at {}:'.format(hex(SUPPLY_CHAIN_SECRET_ADDRESS)))
    print(lines)

def parse_secrets(lines):
    buf = bytearray()
    for line in lines:
        line = line.strip()
        parts = line.split(': ')
        hex_bytes = parts[1].split(' ')
        for h in hex_bytes:
            i = int(h, 16)
            buf.append(i)
    return buf

# If any byte is not 0xFF, then this has been provisioned already
def is_already_provisioned(secrets):
    return any(map(lambda b: b != 0xFF, secrets))

def get_secrets():
    init_device()

    cmd = bytes('mdb {} 256\r'.format(hex(BL_NVROM_BASE)), 'utf-8')
    tn.write(cmd)
    be = bytes('{}: (.*)\r'.format(hex(BL_NVROM_BASE)), 'utf-8')
    result = tn.expect([b'>'])[2].decode('utf-8')
    lines = result.split('\r\n')[1:]
    lines = lines[:-2]
    return lines

def print_secrets():
    lines = get_secrets()
    lines = '\n'.join(lines)
    print('\nPassport Secrets Memory:')
    print(lines)

def save_secrets():
    secrets_text = get_secrets()
    secrets = parse_secrets(secrets_text)
    if secrets and len(secrets) == 256:
        fn = 'secrets.bin'
        try:
            with open(fn, 'wb') as fd:
                fd.write(secrets)
                print('\nSecrets saved to: {}'.format(fn))
        except Exception as err:
            print('Error when saving secrets: {}'.format(err))
    else:
        print('\nUnable to read secrets from device!')

def reset_device():
    init_device()

    print('Resetting Device...')
    tn.write(b'reset\r')
    wait_for_prompt()
    print('Done.')

def erase_all_flash():
    init_device()

    print('Erasing all internal flash (bootloader, secrets, firmware, user settings)...')
    tn.write(b'flash erase_address 0x8000000 0x200000\r')
    wait_for_prompt()
    print('Done.')


# In order to readout the secret key generated for supply chain validation:
#
# - The MPU should NOT be configured on initial boot (if SE is blank)
# - The Python script should issue a command like 'mdb 0x01234567 32'


# At a high level, this script will:
#
# - reset halt
# - Flash the firmware to the device
# - Flash the bootloader to the device
# - Reset
# - Wait x seconds for the basic config to complete
#

def main():
    if DIAGNOSTIC_MODE:
        options = [
            '[1] Test Device Connection',
            '[2] Provision Device',
            '[3] Update Bootloader Only (with secrets.bin)',
            '[4] Update Firmware Only',
            '[5] Print Secrets',
            '[6] Save Secrets (to secrets.bin)',
            '[7] Reset Device',
            '[8] Power Device On',
            '[9] Power Device Off',
            '[E] Erase Internal Flash',
            '[Q] Quit'
        ]
    else:
        options = [
            '[1] Test Device Connection',
            '[2] Provision Device',
            '[3] Print Secrets',
            '[4] Reset Device',
            '[5] Power Device On',
            '[6] Power Device Off',
            '[Q] Quit'
        ]

    menu = TerminalMenu(options, title='\nPassport Provisioning Tool\n  Make a selection:')
    exit = False

    while not exit:
        selection = menu.show()

        if DIAGNOSTIC_MODE:
            if selection == 0:
                connect_to_telnet()
                test_device_connection()
            elif selection == 1:
                provision_device(flash_bootloader=True, flash_firmware=True)
            elif selection == 2:
                provision_device(flash_bootloader=True, with_secrets=True)
            elif selection == 3:
                provision_device(flash_firmware=True)
            elif selection == 4:
                print_secrets()
            elif selection == 5:
                save_secrets()
            elif selection == 6:
                reset_device()
            elif selection == 7:
                power_device(True)
            elif selection == 8:
                power_device(False)
            elif selection == 9:
                erase_all_flash()
            elif selection == 10 or selection == None: # Quit
                exit = True
        else:
            if selection == 0:
                connect_to_telnet()
                test_device_connection()
            elif selection == 1:
                provision_device(flash_bootloader=True, flash_firmware=True)
            elif selection == 2:
                print_secrets()
            elif selection == 3:
                reset_device()
            elif selection == 4:
                power_device(True)
            elif selection == 5:
                power_device(False)
            elif selection == 6 or selection == None: # Quit
                exit = True

if __name__ == '__main__':
  main()
else:
   print('File one executed when imported')
