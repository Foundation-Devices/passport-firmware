# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
import telnetlib

HOST = "localhost"

tn = telnetlib.Telnet(HOST, 4444)

print("1")
result = tn.expect(['>'], 10)[2]
print("2: result={}".format(result))
tn.write(b"reset halt\r")
print("3")
result = tn.expect(['>'], 10)[2]
print("4: result={}".format(result))
tn.write(b"flash write_image erase build-Passport/firmware0.bin 0x8000000\r")
print("5")
result = tn.expect(['>'], 10)[2]
print("6: result={}".format(result))

tn.write(b"flash write_image erase build-Passport/firmware1.bin 0x8040000\r")
print("7")
result = tn.expect(['>'], 100)[2]

# TODO: This should not need to be here - someone we have to expect the prompt twice.
# TODO: Is it an extra echo character?  Or is expect() not consuming the input?  Do we also need to read the input?
result = tn.expect(['>'], 100)[2]
print("8: result = {}".format(result))
tn.write(b"reset\r")
print("9")
result = tn.expect(['>'], 10)[2]
result = tn.expect(['>'], 10)[2]
print("10: result = {}".format(result))
tn.write(b"mdb 0x081e0000 20\r")
print("11")
result = tn.expect(["0x081e0000: (.*)\r"])
print("12: result = {}".format(result))
print('Memory at 0x81e0000 = {}'.format(result[1].group(1)))


# In order to readout the public key generated for supply chain validation:
#
# - The initialization code must generate the public key for the device and
#   store it at a known address in RAM.
# - The MPU should NOT be configured on initial boot (if SE is blank)
# - The Python script should issue a command like 'mdb 0x01234567 32' and save the
#   result somewhere (probably POST to a server with a long cookie for auth).


# At a high level, this script will:
#
# - reset halt
# - Flash the firmware to the device
# - reset
# - Wait x seconds for the basic config to complete
# - Read any necessary information from known SRAM locations
# - Post information to our server
# - reset
#
# Disconnect from telnet
#
# Use some other lib to connect to the GPIO board and start factory test
#
# Numato 32 channel GPIO board over USB serial:
#
# - https://numato.com/product/32-channel-usb-gpio-module-with-analog-inputs/ 
# - https://github.com/numato/samplecode/blob/master/RelayAndGPIOModules/USBRelayAndGPIOModules/python/usbgpio16_32/gpioread.py
# - https://github.com/numato/samplecode/blob/master/RelayAndGPIOModules/USBRelayAndGPIOModules/python/usbgpio16_32/gpiowrite.py
# - https://github.com/numato/samplecode/blob/master/RelayAndGPIOModules/USBRelayAndGPIOModules/python/usbgpio16_32/analogread.py

