#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Klassen module
## roles: [domaincontroller_master]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-wizards]

import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
from univention.testing.ucsschool.klasse import Klasse


def main():
    with utu.UCSTestSchool() as schoolenv:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            ou, oudn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))
            klassen = []

            for i in range(2):
                klasse = Klasse(school=ou)
                klasse.create()
                klasse.check_existence(True)
                klasse.check_get()
                klassen.append(klasse)

            klassen[0].check_query([klassen[0].name, klassen[1].name])

            new_attrs = {"name": "K2", "description": "K2 desc"}
            klassen[0].edit(new_attrs)
            new_attrs = {"name": "K3", "description": "K3 desc"}
            klassen[1].edit(new_attrs)

            klassen[0].check_query(["K2", "K3"])

            for klasse in klassen:
                klasse.check_get()
                klasse.check_existence(True)

                klasse.remove()
                klasse.check_existence(False)


if __name__ == "__main__":
    main()
