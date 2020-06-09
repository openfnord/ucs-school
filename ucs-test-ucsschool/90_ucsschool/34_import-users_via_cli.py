#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Import users via CLI
## tags: [apptest,ucsschool,ucsschool_import3]
## roles: [domaincontroller_master]
## exposure: dangerous
## timeout: 21600
## packages:
##   - ucs-school-import

from univention.testing.ucsschool.importusers import import_users_basics

if __name__ == "__main__":
    import_users_basics(use_cli_api=True, use_python_api=False)
