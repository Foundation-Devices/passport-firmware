# Development

This document describes how to develop for Passport.

## Installation

### Get the Source Code
The instructions below assume you are installing into your home folder at `~/`.  You can choose
to install to a different folder, and just update the `cd` commands appropriately.

    cd ~/
    git clone git@github.com:Foundation-Devices/passport-ng.git

### Install Dependencies
Several tools are required for building and debugging Passport.

#### Cross-Compiler Toolchain
    sudo apt install gcc-arm-none-eabi
    cd ~/passport-ng
    make -C mpy-cross

#### Autotools and USB

    sudo apt install autotools-dev
    sudo apt install automake
    sudo apt install libusb-1.0-0-dev
    sudo apt install libtool

#### OpenOCD - On-Chip Debugger
    cd ~/
    git clone https://github.com/ntfreak/openocd.git
    cd ~/openocd/
    ./bootstrap
    ./configure --enable-stlink
    make
    sudo make install

#### RShell - Micropython Shell and REPL
    cd ~/
    git clone https://github.com/dhylands/rshell
    sudo apt install python3-pip
    sudo pip3 install rshell                                  (this should install rshell in /usr/local/ area)

## Building
### Open Shell Windows/Tabs
You will need several shell windows or tabs open to interact with the various tools.

### Build Window

#### Building the Main Firmare
In one shell, make sure that you `cd` to the root `stm32` source folder, e.g., `cd ~/passport-ng/ports/stm32`:

    make BOARD=Passport
    
To include debug symbols for use in `ddd`, run the following:

    make BOARD=Passport DEBUG=1

You should see it building various `.c` files and freezing `.py` files.  Once complete, the final output should look similar to the following:

    LINK build-Passport/firmware.elf
    text	   data	    bss	    dec	    hex	filename
    475304	    792	  57600	 533696	  824c0	build-Passport/firmware.elf
    GEN build-Passport/firmware.dfu
    GEN build-Passport/firmware.hex

#### Code Signing
In order to load the files onto the device, they need to first be signed by two separate keys.
The `cosign` program performs this task, and it needs to be called twice with two separate
private keys.

First, you need to build the `cosign` tool and copy it somewhere in your `PATH`:

    cd ports/stm32/boards/Passport/tools/cosign
    make
    cp x86/release/cosign ~/.local/bin   # You can run `echo $PATH` to see the list of possible places you can put this file


Next you want to sign the firmware twice.  The `cosign` tool appends `-signed` to the end of the main filename each time it signs.
Assuming you are still in the `ports/stm32` folder run the following:

    # TODO: Update once actual signing is implemented
    cosign -f build-Passport/firmware.bin -k 1 -v 0.9 
    cosign -f build-Passport/firmware-signed.bin -k 2

You can also dump the contents of the firmware header with the following command:

    cosign -f build-Passport/firmware-signed-signed.bin -x

#### Building the Bootloader
To build the bootloader do the following:

    cd ports/stm32/boards/Passport/finalbootloader folder
    make

### OpenOCD Server Window
OpenOCD server provides a socket on `localhost:4444` that you can connect to and issue commands.  This server acts as an intermediary between that socket and the board connected over JTAG.

Once the OpenOCD server is running, you can pretty much ignore this window.  You will interact with the OpenOCD client window (see below).  Open a second shell and run the following:

    /usr/local/bin/openocd -f stlink.cfg -c "adapter speed 1000; transport select hla_swd" -f stm32h7x.cfg

You should see output similar to the following:

    Open On-Chip Debugger 0.10.0+dev-01383-gd46f28c2e-dirty (2020-08-24-08:31)
    Licensed under GNU GPL v2
    For bug reports, read
        http://openocd.org/doc/doxygen/bugs.html
    hla_swd
    Info : The selected transport took over low-level target control. The results might differ compared to plain JTAG/SWD
    Info : Listening on port 6666 for tcl connections
    Info : Listening on port 4444 for telnet connections
    Info : clock speed 1800 kHz
    Info : STLINK V2J29S7 (API v2) VID:PID 0483:3748
    Info : Target voltage: 2.975559
    Info : stm32h7x.cpu0: hardware has 8 breakpoints, 4 watchpoints
    Info : starting gdb server for stm32h7x.cpu0 on 3333
    Info : Listening on port 3333 for gdb connections

### OpenOCD Client Window (aka `telnet` Window)
We use `telnet` to connect to the OpenOCD Server.  Open a third shell and run the following:

    telnet localhost 4444

From here can connect over JTAG and run a range of commands (see the help for OpenOCD for details):

Whenever you change any code in the `finalbootlaoder` folder or in the `common` folder, you will need to rebuild the bootloader (see above), and then flash it to the device with the following sequence in OpenOCD:

    reset halt
    flash write_image erase boards/Passport/finalbootloader/bootloader.bin 0x8000000
    reset

The following command sequence is one you will run repeatedly (i.e., after each build):

    reset halt
    flash write_image erase build-Passport/firmware-signed-signed.bin 0x8020000 
    reset

These commands do the following:

- Stop execution of code on the MCU
- Write part 0 of the firmware to flash at address 0x8000000
- Write part 1 of the firmware to flash at address 0x8040000
- Reset the MCU and start executing code at address 0x8000000

### RShell Window
We use `rshell` to connect to the MicroPython device over USB serial.  Open another shell and run:

    sudo rshell -p /dev/ttyUSB0

This gives us an interactive shell where we can do things like inspect the flash file system, or run a REPL:

- `ls -la /flash` - Get a listing of the files in `/flash` on the device
- `cp local_folder/my_math.py /flash` - Copy a local file into `/flash`
- `repl` - Open a MicroPython REPL.  If there are any files in `/flash`, you can import them.  For example:

```
import my_math
my_math.add(1, 2)
```



