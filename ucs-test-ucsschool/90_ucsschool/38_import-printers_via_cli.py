#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Import printers via CLI
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import

from univention.testing.ucsschool.importprinters import import_printers_basics

if __name__ == "__main__":
    import_printers_basics(use_cli_api=True, use_python_api=False)
