#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: test purge script
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [45467]

import copy
import datetime
import random
import subprocess
import sys

from ldap.filter import escape_filter_chars

import univention.testing.strings as uts
import univention.testing.utils as utils
from ucsschool.importer.configuration import setup_configuration
from ucsschool.importer.factory import setup_factory
from ucsschool.importer.frontend.user_import_cmdline import UserImportCommandLine
from ucsschool.importer.models.import_user import ImportUser
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    def run_purge_script(self):
        cmd = ["/usr/share/ucs-school-import/scripts/ucs-school-purge-expired-users", "-v"]
        sys.stdout.flush()
        sys.stderr.flush()
        exitcode = subprocess.call(cmd)
        self.log.info("Purge process exited with exit code %r", exitcode)
        return exitcode

    def test(self):
        """
        Bug #45467: use purge script to remove users with a ucsschoolPurgeTimestamp in
        the past from multiple OUs

        This uses the case "2/3: delete later, deactivate now" from 216_import-users_delete_variants.
        """
        self.log.info("*** Creating a student, teacher, staff and teacher_and_staff in each OU...")
        source_uid = "source_uid-{}".format(uts.random_string())
        config = copy.deepcopy(self.default_config)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)
        config.update_entry("deletion_grace_period:deactivation", 0)
        config.update_entry("deletion_grace_period:deletion", random.randint(1, 20))

        person_list = list()
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            for ou in (self.ou_A, self.ou_B, self.ou_C):
                person = Person(ou.name, role)
                record_uid = "record_uid-%s" % (uts.random_string(),)
                person.update(record_uid=record_uid, source_uid=source_uid)
                person_list.append(person)
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config])
        wait_for_drs_replication("cn={}".format(escape_filter_chars(person_list[-1].username)))
        self.check_new_and_removed_users(12, 0)

        for person in person_list:
            person.verify()
        self.log.info("*** OK: Created all %r users correctly.", len(person_list))

        self.log.info("*** Setting up import framework...")
        import_config_args = {"dry_run": False, "source_uid": "TestDB", "verbose": True}
        ui = UserImportCommandLine()
        config_files = ui.configuration_files
        config = setup_configuration(config_files, **import_config_args)
        ui.setup_logging(config["verbose"], config["logfile"])
        setup_factory(config["factory"])

        for person in person_list:
            self.log.info("*** Setting purge date for user %r...", person.username)
            exp_days = random.randint(1, 20)
            exp_date = (datetime.datetime.now() - datetime.timedelta(days=exp_days)).strftime("%Y-%m-%d")
            ldap_exp_date = self.pugre_timestamp_udm2ldap(exp_date)
            self.log.debug(
                "Account deletion timestamp for %r is %r (%r).", person.username, exp_date, ldap_exp_date
            )
            user = ImportUser.from_dn(person.dn, person.school, self.lo)
            user.set_purge_timestamp(exp_date)
            user.modify(self.lo)
            self.log.info("*** Verifying purge date...")
            utils.verify_ldap_object(
                person.dn,
                expected_attr={"ucsschoolPurgeTimestamp": [ldap_exp_date]},
                strict=False,
                should_exist=True,
            )
        self.log.info("*** OK: All users purge timestamp set correctly.")
        self.save_ldap_status()

        self.log.info("*** Now running purge script...")
        if self.run_purge_script():
            utils.fail("Error running purge script.")

        self.check_new_and_removed_users(0, 12)
        for person in person_list:
            person.set_mode_to_delete()
            person.verify()
        self.log.info("*** OK: All users were deleted.")


if __name__ == "__main__":
    Test().run()
