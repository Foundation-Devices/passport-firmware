# MicroPython Port To The Nordic Semiconductor nRF Series

This is a port of MicroPython to the Nordic Semiconductor nRF series of chips.

## Supported Features

* UART
* SPI
* LEDs
* Pins
* ADC
* I2C
* PWM (nRF52 only)
* Temperature
* RTC (Real Time Counter. Low-Power counter)
* BLE support including:
  * Peripheral role on nrf51 targets
  * Central role and Peripheral role on nrf52 targets
  * _REPL over Bluetooth LE_ (optionally using WebBluetooth)
  * ubluepy: Bluetooth LE module for MicroPython
  * 1 non-connectable advertiser while in connection

## Tested Hardware

* nRF51
  * [micro:bit](http://microbit.org/)
  * PCA10000 (dongle)
  * PCA10001
  * PCA10028
  * PCA10031 (dongle)
  * [WT51822-S4AT](http://www.wireless-tag.com/wireless_module/BLE/WT51822-S4AT.html)
* nRF52832
  * [PCA10040](http://infocenter.nordicsemi.com/index.jsp?topic=%2Fcom.nordic.infocenter.nrf52%2Fdita%2Fnrf52%2Fdevelopment%2Fnrf52_dev_kit.html)
  * [Adafruit Feather nRF52](https://www.adafruit.com/product/3406)
  * [Thingy:52](http://www.nordicsemi.com/eng/Products/Nordic-Thingy-52)
  * [Arduino Primo](http://www.arduino.org/products/boards/arduino-primo)
  * [IBK-BLYST-NANO breakout board](https://www.crowdsupply.com/i-syst/blyst-nano)
  * [BLUEIO-TAG-EVIM BLYST Nano Sensor board](https://www.crowdsupply.com/i-syst/blyst-nano)
  * [uBlox EVK-NINA-B1](https://www.u-blox.com/en/product/evk-nina-b1)
* nRF52840
  * [PCA10056](http://www.nordicsemi.com/eng/Products/nRF52840-Preview-DK)
  * [PCA10059](https://www.nordicsemi.com/Software-and-Tools/Development-Kits/nRF52840-Dongle)
  * [Particle Xenon](https://docs.particle.io/xenon/)
* nRF9160
  * [PCA10090](https://www.nordicsemi.com/Software-and-Tools/Development-Kits/nRF9160-DK)

## Compile and Flash

Prerequisite steps for building the nrf port:

    git clone <URL>.git micropython
    cd micropython
    make -C mpy-cross

By default, the PCA10040 (nrf52832) is used as compile target. To build and flash issue the following command inside the ports/nrf/ folder:

    make submodules
    make
    make flash

Alternatively the target board could be defined:

     make BOARD=pca10040
     make BOARD=pca10040 flash

## Compile without LTO enabled

As a space optimization, LTO (Link Time Optimization) has been enabled on all
targets in the nrf-port. The `-flto` linker flag can be toggled easily by using
the argument LTO when building. The example below shows how to disable LTO for
the compilation:

    make BOARD=pca10040 LTO=0

**Note**: There have been several issues with use of LTO in conjunction with
GNU ARM Embedded Toolchain 7.2.1/4Q17. It's recommended to use a toolchain after
this release, for example 7.3.1/2Q18 or 8.2.1/4Q18. The alternative would be to
build the target using the LTO=0 as described above.

## Compile and Flash with Bluetooth Stack

First prepare the bluetooth folder by downloading Bluetooth LE stacks and headers:

     ./drivers/bluetooth/download_ble_stack.sh

If the Bluetooth stacks has been downloaded, compile the target with the following command:

    make BOARD=pca10040 SD=s132

The **make sd** will trigger a flash of the bluetooth stack before that application is flashed. Note that **make sd** will perform a full erase of the chip, which could cause 3rd party bootloaders to also be wiped.

    make BOARD=pca10040 SD=s132 sd

Note: further tuning of features to include in bluetooth or even setting up the device to use REPL over Bluetooth can be configured in the `bluetooth_conf.h`.

## Compile with frozen modules

Frozen modules are Python modules compiled to bytecode and added to the firmware
image, as part of MicroPython. They can be imported as usual, using the `import`
statement. The advantage is that frozen modules use a lot less RAM as the
bytecode is stored in flash, not in RAM like when importing from a filesystem.
Also, frozen modules are available even when no filesystem is present to import
from.

To use frozen modules, put them in a directory (e.g. `freeze/`) and supply
`make` with the given directory. For example:

     make BOARD=pca10040 FROZEN_MPY_DIR=freeze

## Enable MICROPY_VFS_FAT
As the `oofatfs` module is not having header guards that can exclude the implementation compile time, this port provides a flag to enable it explicitly. The MICROPY_VFS_FAT is by default set to 0 and has to be set to 1 if `oofatfs` files should be compiled. This will be in addition of setting `MICROPY_VFS` in mpconfigport.h.

For example:

     make BOARD=pca10040 MICROPY_VFS_FAT=1

## Target Boards and Make Flags

Target Board (BOARD) | Bluetooth Stack (SD)    | Bluetooth Support      | Flash Util
---------------------|-------------------------|------------------------|-------------------------------
microbit             | s110                    | Peripheral             | [PyOCD](#pyocdopenocd-targets)
pca10000             | s110                    | Peripheral             | [Segger](#segger-targets)
pca10001             | s110                    | Peripheral             | [Segger](#segger-targets)
pca10028             | s110                    | Peripheral             | [Segger](#segger-targets)
pca10031             | s110                    | Peripheral             | [Segger](#segger-targets)
wt51822_s4at         | s110                    | Peripheral             | Manual, see [datasheet](https://4tronix.co.uk/picobot2/WT51822-S4AT.pdf) for pinout
pca10040             | s132                    | Peripheral and Central | [Segger](#segger-targets)
feather52            | s132                    | Peripheral and Central | Manual, SWDIO and SWCLK solder points on the bottom side of the board
arduino_primo        | s132                    | Peripheral and Central | [PyOCD](#pyocdopenocd-targets)
ibk_blyst_nano       | s132                    | Peripheral and Central | [IDAP](#idap-midap-link-targets)
idk_blyst_nano       | s132                    | Peripheral and Central | [IDAP](#idap-midap-link-targets)
blueio_tag_evim      | s132                    | Peripheral and Central | [IDAP](#idap-midap-link-targets)
evk_nina_b1          | s132                    | Peripheral and Central | [Segger](#segger-targets)
pca10056             | s140                    | Peripheral and Central | [Segger](#segger-targets)
pca10059             | s140                    | Peripheral and Central | Manual, SWDIO and SWCLK solder points on the sides.
particle_xenon       | s140                    | Peripheral and Central | [Black Magic Probe](#black-magic-probe-targets)
pca10090             | None (bsdlib.a)         | None (LTE/GNSS)        | [Segger](#segger-targets)

## IDAP-M/IDAP-Link Targets

Install the necessary tools to flash and debug using IDAP-M/IDAP-Link CMSIS-DAP Debug JTAG:

[IDAPnRFProg for Linux](https://sourceforge.net/projects/idaplinkfirmware/files/Linux/IDAPnRFProg_1_7_190320.zip/download)
[IDAPnRFProg for OSX](https://sourceforge.net/projects/idaplinkfirmware/files/OSX/IDAPnRFProg_1_7_190320.zip/download)
[IDAPnRFProg for Windows](https://sourceforge.net/projects/idaplinkfirmware/files/Windows/IDAPnRFProg_1_7_190320.zip/download)


## Segger Targets

Install the necessary tools to flash and debug using Segger:

[JLink Download](https://www.segger.com/downloads/jlink#)

[nrfjprog Download](https://www.nordicsemi.com/Software-and-Tools/Development-Tools/nRF5-Command-Line-Tools/Download#infotabs)

note: On Linux it might be required to link SEGGER's `libjlinkarm.so` inside nrfjprog's folder.

## PyOCD/OpenOCD Targets

Install the necessary tools to flash and debug using OpenOCD:

    sudo apt-get install openocd
    sudo pip install pyOCD

## Black Magic Probe Targets

This requires no further dependencies other than `arm-none-eabi-gdb`.

`make deploy` will use gdb to load and run new firmware. See
[this guide](https://github.com/blacksphere/blackmagic/wiki/Useful-GDB-commands)
for more tips about using the BMP with GDB.

## Bluetooth LE REPL

The port also implements a BLE REPL driver. This feature is disabled by default, as it will deactivate the UART REPL when activated. As some of the nRF devices only have one UART, using the BLE REPL free's the UART instance such that it can be used as a general UART peripheral not bound to REPL.

The configuration can be enabled by editing the `bluetooth_conf.h` and set `MICROPY_PY_BLE_NUS` to 1.

When enabled you have different options to test it:
* [NUS Console for Linux](https://github.com/tralamazza/nus_console) (recommended)
* [WebBluetooth REPL](https://aykevl.nl/apps/nus/) (experimental)

Other:
* nRF UART application for IPhone/Android

WebBluetooth mode can also be configured by editing `bluetooth_conf.h` and set `BLUETOOTH_WEBBLUETOOTH_REPL` to 1. This will alternate advertisement between Eddystone URL and regular connectable advertisement. The Eddystone URL will point the phone or PC to download [WebBluetooth REPL](https://aykevl.nl/apps/nus/) (experimental), which subsequently can be used to connect to the Bluetooth REPL from the PC or Phone browser.
