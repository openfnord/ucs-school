#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Print UCS@school installation information
## tags: [apptest, ucsschool]
## exposure: safe
## packages:
##   - ucs-school-import

import os
import sys

from apt.cache import Cache as AptCache

from univention.testing.ucsschool.importusers_cli_v2 import ImportTestbase

itb = ImportTestbase()
apt_cache = AptCache()
pck_s = [
    "{:<40} {}".format(
        pck, apt_cache[pck].installed.version if apt_cache[pck].is_installed else "Not installed"
    )
    for pck in sorted([pck for pck in apt_cache.keys() if "school" in pck])
]
itb.log.info("Installed package versions:\n%s", "\n".join(pck_s))

itb.log.info("=" * 79)

for filename in os.listdir("/etc/apt/sources.list.d/"):
    path = os.path.join("/etc/apt/sources.list.d", filename)
    itb.log.info("Content of %r:\n%s", path, open(path, "rb").read())

itb.log.info("=" * 79)

itb.log.info("UCR:\n%s", "\n".join("{!r}: {!r}".format(k, itb.ucr[k]) for k in sorted(itb.ucr.keys())))

sys.exit(0)
