# SPDX-License-Identifier: GPL-3.0-or-later

import os

from nr2301 import NR2301Client


with NR2301Client(
    "http://192.168.1.1",
    password=os.environ["NR2301_PASSWORD"],
) as router:
    router.login()
    print(router.call("version", "get_ww_version"))
