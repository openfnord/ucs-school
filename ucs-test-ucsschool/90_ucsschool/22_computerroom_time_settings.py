#!/usr/share/ucs-test/runner python
## desc: computerroom module time settings
## roles: [domaincontroller_master, domaincontroller_slave]
## versions:
##  4.0-0: skip
##  4.1-0: fixed
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-computerroom]
## bugs: [40655]

import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
from univention.testing.ucsschool.computerroom import Computers, Room
from univention.testing.umc import Client


def main():
    with utu.UCSTestSchool() as schoolenv:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            school, oudn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))
            tea, tea_dn = schoolenv.create_user(school, is_teacher=True)
            open_ldap_co = schoolenv.open_ldap_connection()

            # importing computers
            computers = Computers(open_ldap_co, school, 2, 0, 0)
            created_computers = computers.create()
            computers_dns = computers.get_dns(created_computers)

            # computer rooms contains the created computers
            room = Room(school, host_members=computers_dns)
            schoolenv.create_computerroom(
                school, name=room.name, description=room.description, host_members=room.host_members
            )
            client = Client(ucr.get("hostname"))
            client.authenticate(tea, "univention")

            room.test_time_settings(client)


if __name__ == "__main__":
    main()
