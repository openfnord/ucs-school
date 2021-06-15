#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Test migration from old-legacy import to new-legacy import
## tags: [apptest,ucsschool,ucsschool_import2]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [41862]

import subprocess

import univention.testing.ucr
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.ucsschool.importusers import ImportFile, UserImport


def main():
    with univention.testing.ucr.UCSTestConfigRegistry() as ucr:
        with utu.UCSTestSchool() as schoolenv:
            ou_name, ou_dn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))
            lo = schoolenv.open_ldap_connection(admin=True)

            print("*\n*** Doing old-legacy import...\n*")
            user_import = UserImport(
                school_name=ou_name, nr_students=3, nr_teachers=3, nr_staff=3, nr_teacher_staff=3
            )
            print(user_import)
            import_file = ImportFile(True, False)
            import_file.cli_path = "/usr/share/ucs-school-import/scripts/ucs-school-import"
            import_file.run_import(user_import)
            user_import.verify()
            cmd_block = [
                "/usr/share/ucs-school-import/scripts/ucs-school-migrate-objects-to-4.1R2",
                "--verbose",
                "--migrate-ous",
                "--migrate-users",
            ]
            print("cmd_block: {}".format(cmd_block))
            retcode = subprocess.call(cmd_block, shell=False)
            if retcode:
                utils.fail("Failed to execute {}. Return code: {}.".format(cmd_block, retcode))
            users_object_classes = (
                (user_import.staff, ("ucsschoolStaff",)),
                (user_import.students, ("ucsschoolStudent",)),
                (user_import.teachers, ("ucsschoolTeacher",)),
                (user_import.teacher_staff, ("ucsschoolStaff", "ucsschoolTeacher")),
            )
            for users, object_classes in users_object_classes:
                for user in users:
                    udm_user = lo.get(user.dn)
                    if not all([kls in udm_user["objectClass"] for kls in object_classes]):
                        utils.fail(
                            "User {} not properly migrated. objectClass={}".format(
                                udm_user, udm_user["objectClass"]
                            )
                        )
                    if udm_user.get("ucsschoolSourceUID") or udm_user.get("ucsschoolRecordUID"):
                        utils.fail(
                            "User {} already has ucsschoolSourceUID or ucsschoolRecordUID.".format(
                                udm_user
                            )
                        )

            print("*\n*** Doing new-legacy import...\n*")
            for user in (
                user_import.staff
                + user_import.students
                + user_import.teachers
                + user_import.teacher_staff
            ):
                user.set_mode_to_modify()
                user.update(legacy_v2=True, record_uid=user.username, source_uid="LegacyDB")
            import_file = ImportFile(True, False)
            import_file.run_import(user_import)
            user_import.verify()

    print("*\n*** Test was successful.\n*")


if __name__ == "__main__":
    main()
