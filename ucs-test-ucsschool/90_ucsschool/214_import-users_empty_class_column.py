#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: do not modify group memberships if no group specified (Bug 42288)
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [42288]

import copy

from ldap.filter import filter_format

import univention.testing.strings as uts
import univention.testing.utils as utils
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    ou_C = None

    def new_config(self):
        config = copy.deepcopy(self.default_config)
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)
        return config, source_uid

    def create_user_w_two_classes(self, role, source_uid, same_ou=True):
        cls1_dn, cls1_name = self.udm.create_group(
            position="cn=klassen,cn=schueler,cn=groups,%s" % (self.ou_A.dn,),
            name="{}-{}".format(self.ou_A.name, uts.random_groupname()),
        )
        if same_ou:
            dn = self.ou_A.dn
            name = self.ou_A.name
            school = self.ou_A.name
        else:
            dn = self.ou_B.dn
            name = self.ou_B.name
            school = sorted([self.ou_A.name, self.ou_B.name])[0]
        cls2_dn, cls2_name = self.udm.create_group(
            position="cn=klassen,cn=schueler,cn=groups,%s" % (dn,),
            name="{}-{}".format(name, uts.random_groupname()),
        )
        person = Person(school, role)
        person.update(
            record_uid=uts.random_username(), source_uid=source_uid, username=uts.random_username()
        )
        if same_ou:
            person.update(school_classes={self.ou_A.name: [cls1_name, cls2_name]})
        else:
            person.update(
                school_classes={self.ou_A.name: [cls1_name], self.ou_B.name: [cls2_name]},
                schools=[self.ou_A.name, self.ou_B.name],
            )
        return person, cls1_dn, cls2_dn

    def import_check_changes(self, config, person_list, class_list, add_user, rm_user):
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)

        self.save_ldap_status()  # save ldap state for later comparison
        self.run_import(["-c", fn_config, "-i", fn_csv])  # start import
        self.check_new_and_removed_users(add_user, rm_user)  # check for new users in LDAP
        # check school classes
        for cls_dn, unique_members in class_list:
            utils.verify_ldap_object(
                cls_dn, expected_attr={"uniqueMember": unique_members}, strict=False, should_exist=True
            )

    def test(self):  # formally test_no_modify_classes_with_empty_class_column()
        """
        Bug #42288: do not modify group memberships if no group specified
        Test cases:
          1. has 2 classes -> import w/o classes -> has 2 classes
          2. has 2 classes -> import w 1 class   -> has 1 class
          3. has 0 classes -> import w/o classes -> has 0 classes
          4. has 2 classes from 2 OUs -> import w/o classes -> has 2 classes from 2 OUs
        """

        self.log.info("*** Test case 1/4: has 2 classes -> import w/o classes -> has 2 classes")
        self.log.info("*** (1/4) Importing new users of all roles and two classes from 1 OU.")
        config, source_uid = self.new_config()
        person_list = []
        class_list = []
        for role in ("student", "teacher", "teacher_and_staff"):
            person, cls1_dn, cls2_dn = self.create_user_w_two_classes(role, source_uid)
            person_list.append(person)
            class_list.extend([(cls1_dn, [person.dn]), (cls2_dn, [person.dn])])
        self.import_check_changes(config, person_list, class_list, 3, 0)

        self.log.info("*** (1/4) Modifying users: setting CSV-input to have no classes.")
        for person in person_list:
            person.update(school_classes={})
        self.log.info("*** (1.1/4) school_classes_keep_if_empty=True -> still have classes")
        config.update_entry("school_classes_keep_if_empty", True)
        self.import_check_changes(config, person_list, class_list, 0, 0)
        self.log.info("Test case 1.1/4 was successful.\n\n\n")

        self.log.info("*** (1.2/4) school_classes_keep_if_empty=False -> have no classes")
        config.update_entry("school_classes_keep_if_empty", False)
        class_list_empty = [(dn, []) for dn, persons in class_list]
        self.import_check_changes(config, person_list, class_list_empty, 0, 0)
        self.log.info("Test case 1.2/4 was successful.\n\n\n")

        self.log.info("*** Test case 2/4: has 2 classes -> import w 1 class -> has 1 class")
        self.log.info("*** (2.1/4) Importing new users of all roles and two classes from 1 OU.")
        config, source_uid = self.new_config()
        person_list = []
        class_list = []
        for role in ("student", "teacher", "teacher_and_staff"):
            person, cls1_dn, cls2_dn = self.create_user_w_two_classes(role, source_uid)
            person_list.append(person)
            class_list.extend([(cls1_dn, [person.dn]), (cls2_dn, [person.dn])])
        self.import_check_changes(config, person_list, class_list, 3, 0)

        self.log.info("*** (2.2/4) Modifying users: setting CSV-input to have 1 class.")
        # remove 2nd class
        class_list = []
        for person in person_list:
            classes = person.school_classes[self.ou_A.name]
            person.update(school_classes={self.ou_A.name: [classes[0]]})
            class_dn = self.lo.searchDn(
                filter=filter_format("cn=%s", (classes[0],)),
                base=filter_format("cn=klassen,cn=schueler,cn=groups,%s", (self.ou_A.dn,)),
            )[0]
            class_list.append((class_dn, [person.dn]))
        self.import_check_changes(config, person_list, class_list, 0, 0)
        self.log.info("Test case 2/4 was successful.\n\n\n")

        self.log.info("*** Test case 3/4: has 0 classes -> import w/o classes -> has 0 classes")
        self.log.info("*** (3/4) Importing new users and 0 classes.")
        config, source_uid = self.new_config()
        person_list = []
        class_list = []
        for role in ("student", "teacher", "teacher_and_staff"):
            person, cls1_dn, cls2_dn = self.create_user_w_two_classes(role, source_uid)
            person.update(school_classes={}, username=uts.random_username())
            person_list.append(person)
            class_list.extend([(cls1_dn, []), (cls2_dn, [])])
        self.import_check_changes(config, person_list, class_list, 3, 0)
        self.log.info("Test case 3/4 was successful.\n\n\n")

        self.log.info(
            "*** Test case 4/4: has 2 classes from 2 OUs -> import w/o classes -> has 2 classes from 2 "
            "OUs."
        )
        self.log.info("*** (4.1/4) Importing new users and 1 class from each of 2 OUs.")
        config, source_uid = self.new_config()
        person_list = []
        class_list = []
        for role in ("student", "teacher", "teacher_and_staff"):
            person, cls1_dn, cls2_dn = self.create_user_w_two_classes(role, source_uid, False)
            person_list.append(person)
            class_list.extend([(cls1_dn, [person.dn]), (cls2_dn, [person.dn])])
        self.import_check_changes(config, person_list, class_list, 3, 0)

        self.log.info("*** (4.2/4) Modifying users: setting CSV-input to have no classes.")
        self.log.info(
            "*** Test case 4.2.1/4: has 2 classes from 2 OUs -> import w/o classes & "
            "school_classes_keep_if_empty=True -> has 2 classes from 2 OUs."
        )
        for person in person_list:
            person.update(school_classes={})
        config.update_entry("school_classes_keep_if_empty", True)
        self.import_check_changes(config, person_list, class_list, 0, 0)
        self.log.info("Test case 4.2.1/4 was successful.\n\n\n")

        self.log.info(
            "*** Test case 4.2.2/4: has 2 classes from 2 OUs -> import w/o classes & "
            "school_classes_keep_if_empty=False -> has 0 classes."
        )
        for person in person_list:
            person.update(school_classes={})
        config.update_entry("school_classes_keep_if_empty", False)
        class_list_empty = [(dn, []) for dn, persons in class_list]
        self.import_check_changes(config, person_list, class_list_empty, 0, 0)
        self.log.info("*** Test case 4.2.2/4 was successful.")
        self.log.info("*** Test case 4/4 was successful.\n")


if __name__ == "__main__":
    Test().run()
