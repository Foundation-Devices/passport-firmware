# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# sw_wallets.py - Software wallet config data for all supported wallets
#

from data_codecs.qr_type import QRType
from .bitcoin_core import BitcoinCoreWallet
from .bluewallet import BlueWallet
from .btcpay import BtcPayWallet
# from .casa import CasaWallet
# from .caravan import CaravanWallet
# from .dux_reserve import DuxReserveWallet
from .electrum import ElectrumWallet
# from .fullynoded import FullyNodedWallet
# from .gordian import GordianWallet
# from .lily import LilyWallet
from .sparrow import SparrowWallet
from .specter import SpecterWallet
from .wasabi import WasabiWallet

# Array of all supported software wallets and their attributes -- used to build wallet menus and drive their behavior
supported_software_wallets = [
    BitcoinCoreWallet,
    BlueWallet,
    BtcPayWallet,
    # CaravanWallet,
    # CasaWallet,
    # DuxReserveWallet,
    ElectrumWallet,
    # FullyNodedWallet,
    # GordianWallet,
    # LilyWallet,
    SparrowWallet,
    SpecterWallet,
    WasabiWallet,
]