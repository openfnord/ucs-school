#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: test deletion of users home directory by listener module
## roles: [domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1]
## bugs: [41989]
## packages: [ucs-school-old-homedirs]
## exposure: dangerous

import os
import time
from pwd import getpwnam

from ldap.filter import escape_filter_chars

import univention.testing.ucsschool.ucs_test_school as utu
from ucsschool.lib.models.school import School
from ucsschool.lib.models.user import User
from univention.testing import utils
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    ou_A = None
    ou_B = None
    ou_C = None

    def create_ous(self, schoolenv):
        self.log.info("Creating OUs...")
        self.ou_A = utu.Bunch(name=None, dn=None)
        self.ou_B = utu.Bunch(name=None, dn=None)
        self.ou_A.name, self.ou_A.dn = schoolenv.create_ou(name_edudc=self.ucr.get("hostname"))
        # not using the cache, as it could return the same OU on single Primary Directory Nodes
        self.ou_B.name, self.ou_B.dn = schoolenv.create_ou(use_cache=False)
        self.log.info(
            "*** This host is responsible for OU %r, but not for OU %r.", self.ou_A.name, self.ou_B.name
        )
        all_local_schools = [school.dn for school in School.get_all(self.lo)]
        self.log.info("*** This hosts school OUs: %r\n\n", all_local_schools)
        if self.ou_B.name in all_local_schools:
            utils.fail("Found OU %r in local schools." % self.ou_B.name)

    def test(self):
        for role in ("student", "teacher", "teacher_and_staff"):
            self.log.info("*** Creating user 1 with role %r in OU %r", role, self.ou_A.name)
            kwargs = dict(ou_name=self.ou_A.name, schools=[self.ou_A.name])
            if role in ["teacher", "teacher_and_staff"]:
                kwargs["is_teacher"] = True
            if role in ["staff", "teacher_and_staff"]:
                kwargs["is_staff"] = True
            username1, userdn1 = self.schoolenv.create_user(**kwargs)

            self.log.info(
                "*** Creating user 2 with role %r in OUs %r", role, [self.ou_A.name, self.ou_B.name]
            )
            kwargs = dict(ou_name=self.ou_A.name, schools=[self.ou_A.name, self.ou_B.name])
            if role in ["teacher", "teacher_and_staff"]:
                kwargs["is_teacher"] = True
            if role in ["staff", "teacher_and_staff"]:
                kwargs["is_staff"] = True
            username2, userdn2 = self.schoolenv.create_user(**kwargs)
            user1 = User.from_dn(userdn1, None, self.lo)
            user2 = User.from_dn(userdn2, None, self.lo)
            homedir1 = user1.get_udm_object(self.lo)["unixhome"]
            homedir2 = user2.get_udm_object(self.lo)["unixhome"]
            self.log.debug("homedir1=%r", homedir1)
            self.log.debug("homedir2=%r", homedir2)
            os.makedirs(homedir1, 0o0711)
            os.makedirs(homedir2, 0o0711)
            try:
                os.chown(homedir1, getpwnam(username1).pw_uid, getpwnam(username1).pw_gid)
                os.chown(homedir2, getpwnam(username2).pw_uid, getpwnam(username2).pw_gid)
            except KeyError as exc:
                self.log.error(
                    "*** getpwnam() failure -> user not found -> probably replication error: %s", exc
                )
                self.log.error("*** if test fails now, it's because of this")
            if not (os.path.exists(homedir1) and os.path.isdir(homedir1)):
                utils.fail("Homedir 1 %r was not created." % homedir1)
            else:
                self.log.info("Created homedir 1 %r: %r", homedir1, os.stat(homedir1))
            if not (os.path.exists(homedir2) and os.path.isdir(homedir2)):
                utils.fail("Homedir 2 %r was not created." % homedir2)
            else:
                self.log.info("Created homedir 2 %r: %r", homedir2, os.stat(homedir2))
            time.sleep(30)

            self.log.info(
                "*** Deleting %r 1 %r, should remove home directory %r on this host...",
                role,
                user1,
                homedir1,
            )
            user1.remove(self.lo)
            utils.wait_for_replication_and_postrun()
            if os.path.exists(homedir1):
                utils.fail("Homedir 1 %r was not removed." % homedir1)
            self.log.info("OK 1: homedir %r was removed.", homedir1)

            self.log.info(
                "*** Removing %r 2 %r from OU %r, should remove home directory %r on this host...",
                role,
                user2,
                self.ou_A.name,
                homedir2,
            )
            wait_for_drs_replication("cn={}".format(escape_filter_chars(username2)))
            user2.remove_from_school(self.ou_A.name, self.lo)
            user2.modify(self.lo)
            utils.wait_for_replication_and_postrun()
            if os.path.exists(homedir2):
                utils.fail("Homedir 2 %r was not removed." % homedir2)
            self.log.info("OK 2: homedir %r was removed.", homedir2)


if __name__ == "__main__":
    Test().run()
