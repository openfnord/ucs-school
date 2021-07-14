#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: test recursive dependency solver for formatting ImportUser properties
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [42137]

import copy
import random
import time

from ldap.filter import escape_filter_chars

import univention.testing.strings as uts
import univention.testing.utils as utils
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester

username_max_length = {"default": 20, "student": 15}


class ExtAttrPerson(Person):
    def __init__(self, school, role, ext_attr_name):
        super(ExtAttrPerson, self).__init__(school, role)
        self.extattr = time.strftime("%Y-%m-%d")
        self.ext_attr_name = ext_attr_name

    def map_to_dict(self, value_map):
        result = super(ExtAttrPerson, self).map_to_dict(value_map)
        result[value_map.get(self.ext_attr_name, "__EMPTY__")] = self.extattr
        if "__EMPTY__" in result.keys():
            del result["__EMPTY__"]
        return result

    def expected_attributes(self):
        result = super(ExtAttrPerson, self).expected_attributes()
        result["univentionFreeAttributes15"] = [self.extattr]


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def test(self):
        ext_attr_name = uts.random_name()
        properties = {
            "position": self.udm.UNIVENTION_CONTAINER,
            "name": uts.random_name(),
            "shortDescription": uts.random_string(),
            "CLIName": ext_attr_name,
            "module": "users/user",
            "objectClass": "univentionFreeAttributes",
            "ldapMapping": "univentionFreeAttribute15",
            "mayChange": 1,
        }
        self.udm.create_object("settings/extended_attribute", **properties)

        source_uid = "{}-{:02}-{:02}".format(
            random.randint(1900, 2016), random.randint(1, 12), random.randint(1, 27)
        )
        config = copy.deepcopy(self.default_config)
        del config["csv"]["mapping"]
        config.update_entry("csv:mapping:Nach", "lastname")
        config.update_entry("csv:mapping:OUs", "schools")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("scheme:birthday", "<source_uid>")  # lib attr that depends on lib attr
        config.update_entry(
            "scheme:record_uid", "<email>.<city>[0:4]"
        ),  # lib attr that depends on UDM prop & lib attr
        config.update_entry(
            "scheme:email", "<{}>@<maildomain><:strip>".format(ext_attr_name)
        ),  # lib attr that
        # depends on lib attr, not-lib-mapped extended attr and kwargs (maildomain)
        config.update_entry(
            "scheme:username:default", "<firstname:lower>.<birthday>"
        ),  # lib attr that depends on lib attrs
        config.update_entry(
            "scheme:firstname", "fn-<lastname>[1:6]"
        ),  # lib attr that depends on lib attr
        config.update_entry(
            "scheme:street", "<:lower><firstname>-<lastname>"
        ),  # not a dependency of other prop, but
        # should be set on user obj anyway
        config.update_entry("scheme:phone", "<birthday>"),  # UDM prop that depends on lib attr
        config.update_entry(
            "scheme:roomNumber", "<phone>-<email>[0:5]"
        ),  # UDM prop that depends on other UDM prop
        config.update_entry("scheme:city", "<birthday>"),  # UDM prop that depends on lib attr
        config.update_entry(
            "scheme:{}".format(ext_attr_name), "<firstname:lower>.<lastname:lower>"
        )  # not-lib-mapped extended attr that depends on lib attrs
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)

        self.log.info("Importing a user from each role...")
        person_list = list()
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = ExtAttrPerson(self.ou_A.name, role, ext_attr_name)
            person.update(
                source_uid=source_uid,
                lastname=uts.random_username(),
                birthday=None,  # emtpy, so that it will be generated from scheme
                record_uid=None,
                mail=None,
                username=None,
                firstname=None,
                extattr=None,
                school_classes={},  # no mapping for auto generated classes
            )
            person_list.append(person)
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config])
        for person in person_list:
            firstname = "fn-{}".format(person.lastname[1:6])
            extattr_value = "{}.{}".format(firstname.lower(), person.lastname.lower())
            birthday = source_uid
            # email = '{}@{}'.format('{}.{}'.format(firstname, person.lastname).lower(), self.maildomain)
            email = "{}@{}".format(extattr_value, self.maildomain)
            name_length = username_max_length.get(person.role, username_max_length["default"])
            name = "{}.{}".format(firstname.lower(), birthday).replace("-", "")[:name_length]
            person.city = birthday
            record_uid = "{}.{}".format(email, person.city[:4])
            person.street = "{}-{}".format(firstname, person.lastname)
            person.phone = birthday
            person.room = "{}-{}".format(person.phone, email[:5])
            person.update(
                firstname=firstname,
                birthday=birthday,
                mail=email,
                username=name,
                record_uid=record_uid,
                extattr=extattr_value,
            )
        wait_for_drs_replication("cn={}".format(escape_filter_chars(person_list[-1].username)))
        self.check_new_and_removed_users(4, 0)
        for person in person_list:
            person.verify()
            utils.verify_ldap_object(
                person.dn,
                {
                    "street": [person.street],
                    "telephoneNumber": [person.phone],
                    "roomNumber": [person.room],
                    "l": [person.city],
                },
            )
        self.log.info("*** OK: All %r users were created correctly.", len(person_list))


if __name__ == "__main__":
    Test().run()
