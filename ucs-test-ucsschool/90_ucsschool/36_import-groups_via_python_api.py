#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Import groups via python API
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import

from univention.testing.ucsschool.importgroups import import_groups_basics

if __name__ == "__main__":
    import_groups_basics(use_cli_api=False, use_python_api=True)
