# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# log.py - Log file functionality that writes to the console via print() and, if available, also writes to the SD card
#          appending to a file named log.log.
#

def log(msg):
    from files import CardSlot, CardMissingError

    # Always write to console
    print(msg)

    # Then try the microSD card, but it's fine if not present
    try:
        with CardSlot() as card:
            fname, nice = card.get_file_path('log.log')
            with open(fname, 'a') as fd:
                fd.write(msg + '\n')
    except Exception:
        pass
