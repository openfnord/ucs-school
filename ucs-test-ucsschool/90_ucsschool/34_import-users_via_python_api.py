#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Import users via python API
## tags: [apptest,ucsschool,ucsschool_import2]
## roles: [domaincontroller_master]
## exposure: dangerous
## timeout: 36000
## packages:
##   - ucs-school-import

from univention.testing.ucsschool.importusers import import_users_basics

if __name__ == "__main__":
    import_users_basics(use_cli_api=False, use_python_api=True)
