#!/usr/share/ucs-test/runner python
## desc: Test umc calls to generate school class lists
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-groups]

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.umc import Client


def main():
    ucr = ucr_test.UCSTestConfigRegistry()
    ucr.load()
    host = ucr.get("hostname")
    with utu.UCSTestSchool() as schoolenv:
        school_name, oudn = schoolenv.create_ou(name_edudc=host)
        class_name, class_dn = schoolenv.create_school_class(school_name)
        stu_firstname = uts.random_string()
        stu_lastname = uts.random_string()
        stu, studn = schoolenv.create_user(
            school_name, classes=class_name, firstname=stu_firstname, lastname=stu_lastname
        )

        account = utils.UCSTestDomainAdminCredentials()
        admin = account.username
        passwd = account.bindpw

        connection = Client(host, language="en_US")
        connection.authenticate(admin, passwd)
        for separator in [",", "\t"]:
            options = {"school": school_name, "group": class_dn, "separator": separator}
            class_list = connection.umc_command("schoollists/csvlist", options).result
            expected_class_list = {
                u"csv": u"Firstname{sep}Lastname{sep}Class{sep}Username\r\n{first}{sep}{last}{sep}{cls_name}{sep}{uid}\r\n".format(
                    sep=separator,
                    first=stu_firstname,
                    last=stu_lastname,
                    cls_name=class_name.replace(school_name + "-", "", 1),
                    uid=stu,
                ),
                u"filename": u"{}.csv".format(class_name),
            }
            print("Expected: {}".format(expected_class_list))
            print("Received: {}".format(class_list))
            assert class_list == expected_class_list


if __name__ == "__main__":
    main()
