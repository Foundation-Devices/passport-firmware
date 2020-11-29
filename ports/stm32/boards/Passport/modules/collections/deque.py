# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# See also: <https://github.com/micropython/micropython-lib/blob/master/LICENSE>
#
class deque:

    def __init__(self, iterable=None):
        if iterable is None:
            self.q = []
        else:
            self.q = list(iterable)

    def popleft(self):
        return self.q.pop(0)

    def popright(self):
        return self.q.pop()

    def pop(self):
        return self.q.pop()

    def append(self, a):
        self.q.append(a)

    def appendleft(self, a):
        self.q.insert(0, a)

    def extend(self, a):
        self.q.extend(a)

    def __len__(self):
        return len(self.q)

    def __bool__(self):
        return bool(self.q)

    def __iter__(self):
        yield from self.q

    def __str__(self):
        return 'deque({})'.format(self.q)
