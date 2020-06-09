#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Import networks via python API
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import

import sys

from univention.testing.ucsschool.importnetworks import import_networks_basics

if __name__ == "__main__":
    # Not yet implemented
    sys.exit(137)

    import_networks_basics(use_cli_api=False, use_python_api=True)
