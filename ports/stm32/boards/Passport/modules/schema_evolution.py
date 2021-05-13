# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# schema_evolution.py
#
# Update code for converting any stored data formats when moving from an older firmware version to a newer version
#

# NOTE: The goal should be to mostly add to existing formats in a way that doesn't require schema evolution scripts,
#       but sometimes this is not possible, so this hook exists to handle those, hopefully rare, cases.
async def handle_schema_evolutions(update_from_to):
    from common import settings

    parts = update_from_to.split('->')
    from_version = parts[0]
    to_version = parts[1]

    # print('handle_schema_evolutions(): from_version={} -> to_version={}'.format(from_version, to_version))

    # Potentially runs multiple times to handle the case of a user skipping firmware versions with data format changes
    while True:
        if from_version == '0.9.83' and to_version == '0.9.84':
            # Handle evolutions
            from_version = to_version
            continue

        elif from_version == '1.0.2' and to_version == '1.0.3':
            # Handle evolutions
            from_version = to_version
            continue

        # We only reach here if no more evolutions are possible.
        # Remove the update indicator from the settings.
        # NOTE: There is a race condition here, but these evolutions should be extremely fast, and ideally
        #       coded in a way that is idempotent.
        # print('handle_schema_evolutions() Done 1')
        settings.remove('update')
        await settings.save()
        # print('handle_schema_evolutions() Done 1')
        return
