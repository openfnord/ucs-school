#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: test operations on user resource using HTTP interface
## tags: [ucs_school_http_api]
## exposure: dangerous
## packages: [ucs-school-http-api-bb]
## bugs: []

from __future__ import unicode_literals

import random
import time
from multiprocessing import Pool
from unittest import main

import requests

import univention.testing.strings as uts
from ucsschool.lib.models.user import Staff as LibStaff, User as LibUser
from univention.testing.ucsschool.bb_api import (
    RESSOURCE_URLS,
    HttpApiUserTestBase,
    api_call,
    create_remote_static,
    partial_update_remote_static,
)

try:
    from urlparse import urljoin  # py2
except ImportError:
    from urllib.parse import urljoin  # py3


class Test(HttpApiUserTestBase):
    def test_01_list_resource_from_external(self):
        response = requests.get(RESSOURCE_URLS["users"], headers=self.auth_headers)
        res = response.json()
        self.assertIsInstance(res, list, repr(res))
        self.assertIsInstance(res[0], dict, repr(res))
        self.assertIn("name", res[0], repr(res))
        self.assertIn("firstname", res[0], repr(res))

    def test_02_create_user_parallel_from_external_different_classes(self):
        parallelism = 20
        self.logger.info(
            "*** Using OUs %r and %r, parallelism=%d.",
            self.itb.ou_A.name,
            self.itb.ou_B.name,
            parallelism,
        )
        attrs = [
            self.make_user_attrs([self.itb.ou_A.name, self.itb.ou_B.name]) for _i in range(parallelism)
        ]
        for _attr in attrs:
            self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
                self.extract_class_dns(_attr)
            )

        pool = Pool(processes=parallelism)
        job_args = [(self.auth_headers, attr) for attr in attrs]
        t0 = time.time()
        map_async_result = pool.map_async(create_remote_static, job_args)
        results = map_async_result.get()
        t1 = time.time()
        self.logger.info("***** got %d results in %d seconds", len(results), t1 - t0)
        self.logger.debug("***** results=%r", results)
        errors = []
        for r in results:
            try:
                self.schoolenv.udm._cleanup.setdefault("users/user", []).append(r["dn"])
            except KeyError:
                # continue to collect user DNs, so we can cleanup as much as possible
                errors.append("Result without DN: {!r}.".format(r))
        if errors:
            self.fail(" ".join(errors))
        for num, result in enumerate(results, start=1):
            self.logger.info("*** Checking result %d/%d (%r)...", num, parallelism, result["name"])
            user = self.get_import_user(result["dn"])
            self.compare_import_user_and_resource(user, result)
            self.logger.info("*** OK: LDAP <-> resource")
            # now compare with attrs
            for attr in attrs:
                if attr["name"] == user.name:
                    break
            else:
                self.fail("Could not find user with name {!r} in attrs.".format(user.name))
            import_user_cls = user.__class__
            user2 = import_user_cls(**attr)
            user2.disabled = "1" if attr["disabled"] else "0"
            user2.password = ""
            user2.roles = user.roles
            user2.school = self.itb.ou_A.name
            user2.schools = [self.itb.ou_A.name, self.itb.ou_B.name]
            user2.ucsschool_roles = user.ucsschool_roles  # not in attr
            self.compare_import_user_and_resource(user2, result, "ATTR")
            self.logger.info("*** OK: attr <-> resource")

    def test_03_create_user_parallel_from_external_same_classes(self):
        parallelism = 20
        self.logger.info(
            "*** Using OUs %r and %r, parallelism=%d.",
            self.itb.ou_A.name,
            self.itb.ou_B.name,
            parallelism,
        )
        attrs = [
            self.make_user_attrs([self.itb.ou_A.name, self.itb.ou_B.name]) for _i in range(parallelism)
        ]
        for _attr in attrs:
            self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
                self.extract_class_dns(_attr)
            )

        # put everyone (except staff) into same classes
        everyone_classes = {}
        for attr in attrs:
            if attr["school_classes"]:
                everyone_classes = attr["school_classes"]
                # TODO: create bug report for this, or handle in API server:
                # work around school.lib failing when trying to create same class (and share) in two
                # processes
                group_dns = self.extract_class_dns(attr)
                for group_dn in group_dns:
                    self.logger.debug("*** Creating group %r...", group_dn)
                    LibUser.get_or_create_group_udm_object(group_dn, self.lo)
                break
        for attr in attrs:
            if not (len(attr["roles"]) == 1 and "/staff/" in attr["roles"][0]):
                # don't set school_classes on staff
                attr["school_classes"] = everyone_classes
        pool = Pool(processes=parallelism)
        job_args = [(self.auth_headers, attr) for attr in attrs]
        t0 = time.time()
        map_async_result = pool.map_async(create_remote_static, job_args)
        results = map_async_result.get()
        t1 = time.time()
        self.logger.info("***** got %d results in %d seconds", len(results), t1 - t0)
        self.logger.debug("***** results=%r", results)
        errors = []
        for r in results:
            try:
                self.schoolenv.udm._cleanup.setdefault("users/user", []).append(r["dn"])
            except KeyError:
                # continue to collect user DNs, so we can cleanup as much as possible
                errors.append("Result without DN: {!r}.".format(r))
        if errors:
            self.fail(" ".join(errors))
        for num, result in enumerate(results, start=1):
            self.logger.info("*** Checking result %d/%d (%r)...", num, parallelism, result["name"])
            user = self.get_import_user(result["dn"])
            self.compare_import_user_and_resource(user, result)
            self.logger.info("*** OK: LDAP <-> resource")
            # now compare with attrs
            for attr in attrs:
                if attr["name"] == user.name:
                    break
            else:
                self.fail("Could not find user with name {!r} in attrs.".format(user.name))
            import_user_cls = user.__class__
            user2 = import_user_cls(**attr)
            user2.disabled = "1" if attr["disabled"] else "0"
            user2.password = ""
            user2.roles = user.roles
            user2.school = self.itb.ou_A.name
            user2.schools = [self.itb.ou_A.name, self.itb.ou_B.name]
            user2.ucsschool_roles = user.ucsschool_roles  # not in attr
            self.compare_import_user_and_resource(user2, result, "ATTR")
            self.logger.info("*** OK: attr <-> resource")

    def test_04_partial_update_user_parallel_from_external_different_classes(self):
        parallelism = 20
        self.logger.info(
            "*** Using OUs %r and %r, parallelism=%d.",
            self.itb.ou_A.name,
            self.itb.ou_B.name,
            parallelism,
        )
        # create users sequentially and using WSGI interface
        jobs = []
        for _i in range(parallelism):
            create_attrs = self.make_user_attrs(
                [self.itb.ou_A.name, self.itb.ou_B.name],
                school=self.itb.ou_A.name,  # overwrite URLs
                schools=[self.itb.ou_A.name, self.itb.ou_B.name],  # overwrite URLs
            )
            del create_attrs["roles"]
            self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
                self.extract_class_dns(create_attrs)
            )
            user_obj = self.create_import_user(**create_attrs)
            self.logger.info("*** Created: %r", user_obj.to_dict())
            roles = tuple(user_obj.roles)
            if roles == ("pupil",):
                roles = ("student",)
            attrs_new = self.make_user_attrs(
                [self.itb.ou_A.name, self.itb.ou_B.name],
                partial=True,
                name=user_obj.name,
                roles=roles,
                source_uid=user_obj.source_uid,
                record_uid=user_obj.record_uid,
            )
            if isinstance(user_obj, LibStaff):
                create_attrs["school_classes"] = {}
                if "school_classes" in attrs_new:
                    attrs_new["school_classes"] = {}
            self.logger.info("*** attrs_new=%r", attrs_new)
            self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
                self.extract_class_dns(attrs_new)
            )
            jobs.append((create_attrs, attrs_new))

        # modify users in parallel and using HTTP
        pool = Pool(processes=parallelism)
        t0 = time.time()
        map_async_result = pool.map_async(
            partial_update_remote_static, [(self.auth_headers, job[0]["name"], job[1]) for job in jobs]
        )
        results = map_async_result.get()
        t1 = time.time()
        self.logger.info("***** got %d results in %d seconds", len(results), t1 - t0)
        self.logger.debug("***** results=%r", results)
        for num, result in enumerate(results, start=1):
            self.logger.info(
                "*** Checking result %d/%d (%r)...", num, parallelism, result.get("name", "N/A")
            )
            user = self.get_import_user(result["dn"])
            self.compare_import_user_and_resource(user, result)
            self.logger.info("*** OK: LDAP <-> resource")
            # now compare with attrs
            for job in jobs:
                if job[0]["name"] == user.name:
                    attr, new_attrs = job
                    for k, v in new_attrs.items():
                        if k == "school_classes" and not v:
                            # special case `school_classes`: if newly empty but previously
                            # non-empty -> use old value
                            # see end of ImportUser.make_classes()
                            # Bug #48045
                            continue
                        attr[k] = v
                    break
            else:
                self.fail("Could not find user with name {!r} in jobs.".format(user.name))
            import_user_cls = user.__class__
            user2 = import_user_cls(**attr)
            user2.disabled = "1" if attr["disabled"] else "0"
            user2.password = ""
            user2.roles = user.roles
            user2.school = self.itb.ou_A.name
            user2.schools = [self.itb.ou_A.name, self.itb.ou_B.name]
            user2.ucsschool_roles = user.ucsschool_roles  # not in attr
            self.compare_import_user_and_resource(user2, result, "ATTR")
            self.logger.info("*** OK: attr <-> resource")

    def test_05_rename_single_user(self):
        self.logger.info("*** Using OUs %r and %r.", self.itb.ou_A.name, self.itb.ou_B.name)
        name_old = uts.random_username()
        self.logger.info("*** creating user with username %r", name_old)
        create_attrs = self.make_user_attrs(
            [self.itb.ou_A.name],
            school=self.itb.ou_A.name,  # overwrite URLs
            schools=[self.itb.ou_A.name],  # overwrite URLs
            partial=False,
            name=name_old,
        )
        del create_attrs["roles"]
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(create_attrs)
        )
        old_user_obj = self.create_import_user(**create_attrs)
        self.logger.info("*** API call (create) returned: %r", old_user_obj)

        name_new = uts.random_username()
        self.logger.info("*** renaming user from %r to %r", name_old, name_new)
        self.schoolenv.udm._cleanup.setdefault("users/user", []).append(
            old_user_obj.dn.replace(name_old, name_new)
        )
        modify_attrs = {"name": name_new}
        self.logger.info("*** modify_attrs=%r", modify_attrs)
        resource_new = partial_update_remote_static((self.auth_headers, name_old, modify_attrs))
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(name_new, resource_new["name"])
        user = self.get_import_user(resource_new["dn"])
        self.assertEqual(name_new, user.name)
        url = urljoin(RESSOURCE_URLS["users"], name_new + "/")
        self.assertEqual(resource_new["url"], url)
        resource_new2 = api_call("get", url, headers=self.auth_headers)
        self.assertDictEqual(resource_new, resource_new2)
        url = urljoin(RESSOURCE_URLS["users"], name_old + "/")
        response = requests.get(url, headers=self.auth_headers)
        self.assertEqual(response.status_code, 404)
        self.compare_import_user_and_resource(user, resource_new)
        self.logger.info("*** OK: LDAP <-> resource")

    def test_06_create_user_without_name(self):
        self.logger.info("*** Using OUs %r and %r.", self.itb.ou_A.name, self.itb.ou_B.name)
        attrs = self.make_user_attrs([self.itb.ou_A.name, self.itb.ou_B.name])
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(self.extract_class_dns(attrs))
        del attrs["name"]
        self.logger.debug("*** attrs=%r", attrs)
        username_begin = "{}.{}".format(attrs["firstname"], attrs["lastname"])
        result = create_remote_static((self.auth_headers, attrs))
        self.assertEqual(result["name"], username_begin[: len(result["name"])])
        user = self.get_import_user(result["dn"])
        self.assertEqual(user.name, username_begin[: len(user.name)])
        self.compare_import_user_and_resource(user, result)
        self.logger.info("*** OK: LDAP <-> resource")

    def test_07_move_teacher_one_school_only(self):
        self.logger.info(
            "*** Going to move teacher from OU %r to %r ***", self.itb.ou_A.name, self.itb.ou_B.name
        )
        self.logger.info("*** Using OUs %r and %r.", self.itb.ou_A.name, self.itb.ou_B.name)
        create_attrs = self.make_user_attrs([self.itb.ou_A.name], partial=False, roles=("teacher",))
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.assertEqual(create_attrs["school"].strip("/").split("/")[-1], self.itb.ou_A.name)
        self.assertEqual(create_attrs["schools"], [create_attrs["school"]])
        self.assertListEqual(create_attrs["school_classes"].keys(), [self.itb.ou_A.name])
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(create_attrs)
        )

        create_result = create_remote_static((self.auth_headers, create_attrs))
        self.logger.debug("*** create_result=%r", create_result)
        self.assertEqual(create_result["name"], create_attrs["name"])
        self.assertEqual(create_result["school"].strip("/").split("/")[-1], self.itb.ou_A.name)
        self.assertListEqual(create_result["schools"], [create_result["school"]])
        self.assertDictEqual(create_result["school_classes"], create_attrs["school_classes"])

        user_old = self.get_import_user(create_result["dn"])
        self.logger.debug("*** user_old.school_classes=%r", user_old.school_classes)
        user_old_udm = user_old.get_udm_object(self.lo)
        old_groups = user_old_udm["groups"]
        self.logger.info("*** old_groups=%r", old_groups)
        for grp in old_groups:
            self.assertIn(self.itb.ou_A.name, grp)
            self.assertNotIn(self.itb.ou_B.name, grp)

        modify_attrs = {
            "school": create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name),
            "schools": [create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name)],
            "school_classes": {
                self.itb.ou_B.name: sorted([uts.random_username(4), uts.random_username(4)])
            },
        }
        self.logger.info("*** modify_attrs=%r", modify_attrs)

        resource_new = partial_update_remote_static(
            (self.auth_headers, create_result["name"], modify_attrs)
        )
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(create_result["name"], resource_new["name"])
        self.assertDictEqual(modify_attrs["school_classes"], resource_new["school_classes"])

        user = self.get_import_user(resource_new["dn"])
        self.logger.debug("*** user.school_classes=%r", user.school_classes)
        self.assertEqual(create_result["name"], user.name)
        url = urljoin(RESSOURCE_URLS["users"], create_result["name"] + "/")
        self.assertEqual(resource_new["url"], url)

        resource_new2 = api_call("get", url, headers=self.auth_headers)
        self.assertDictEqual(resource_new, resource_new2)

        self.compare_import_user_and_resource(user, resource_new)
        self.logger.info("*** OK: LDAP <-> resource")

        user_new_udm = user.get_udm_object(self.lo)
        new_groups = user_new_udm["groups"]
        self.logger.info("*** new_groups=%r", new_groups)
        for grp in new_groups:
            self.assertIn(self.itb.ou_B.name, grp)
            self.assertNotIn(self.itb.ou_A.name, grp)

    def test_08_move_teacher_remove_primary(self):
        self.logger.info(
            "*** Going to create teacher in OUs %r and %r, then remove it from primary (%r). ***",
            self.itb.ou_A.name,
            self.itb.ou_B.name,
            self.itb.ou_A.name,
        )
        self.logger.info("*** Using OUs %r and %r.", self.itb.ou_A.name, self.itb.ou_B.name)
        create_attrs = self.make_user_attrs(
            [self.itb.ou_A.name, self.itb.ou_B.name], partial=False, roles=("teacher",)
        )
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.assertEqual(create_attrs["school"].strip("/").split("/")[-1], self.itb.ou_A.name)
        self.assertEqual(
            [
                create_attrs["schools"][0].strip("/").split("/")[-1],
                create_attrs["schools"][1].strip("/").split("/")[-1],
            ],
            [self.itb.ou_A.name, self.itb.ou_B.name],
        )
        self.assertSetEqual(
            set(create_attrs["school_classes"].keys()), {self.itb.ou_A.name, self.itb.ou_B.name}
        )
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(create_attrs)
        )

        create_result = create_remote_static((self.auth_headers, create_attrs))
        self.logger.debug("*** create_result=%r", create_result)
        self.assertEqual(create_result["name"], create_attrs["name"])
        self.assertEqual(create_result["school"], create_attrs["school"])
        self.assertSetEqual(set(create_result["schools"]), set(create_attrs["schools"]))
        self.assertDictEqual(create_result["school_classes"], create_attrs["school_classes"])

        user_old = self.get_import_user(create_result["dn"])
        self.logger.debug("*** user_old.school_classes=%r", user_old.school_classes)
        user_old_udm = user_old.get_udm_object(self.lo)
        old_groups = user_old_udm["groups"]
        self.logger.info("*** old_groups=%r", old_groups)
        for grp_name in (
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_B.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_B.name),
        ):
            assert any(dn.startswith(grp_name) for dn in old_groups)

        create_attrs_school_classes = dict(
            (ou, ["{}-{}".format(ou, k) for k in kls])
            for ou, kls in create_attrs["school_classes"].items()
        )
        self.logger.info("*** user_old.school_classes    =%r", user_old.school_classes)
        self.logger.info("*** create_attrs_school_classes=%r", create_attrs_school_classes)
        self.assertDictEqual(user_old.school_classes, create_attrs_school_classes)

        modify_attrs = {
            "school": create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name),
            "schools": [create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name)],
            "school_classes": {
                self.itb.ou_B.name: sorted([uts.random_username(4), uts.random_username(4)])
            },
        }
        self.logger.info("*** modify_attrs=%r", modify_attrs)

        resource_new = partial_update_remote_static(
            (self.auth_headers, create_result["name"], modify_attrs)
        )
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(create_result["name"], resource_new["name"])
        self.assertDictEqual(modify_attrs["school_classes"], resource_new["school_classes"])

        self.logger.debug("*** zzz...")
        time.sleep(10)

        user = self.get_import_user(resource_new["dn"])
        self.logger.debug("*** user.school_classes=%r", user.school_classes)
        self.assertEqual(create_result["name"], user.name)
        url = urljoin(RESSOURCE_URLS["users"], create_result["name"] + "/")
        self.assertEqual(resource_new["url"], url)

        resource_new2 = api_call("get", url, headers=self.auth_headers)
        self.assertDictEqual(resource_new, resource_new2)

        self.compare_import_user_and_resource(user, resource_new)
        self.logger.info("*** OK: LDAP <-> resource")

        user_new_udm = user.get_udm_object(self.lo)
        new_groups = user_new_udm["groups"]
        self.logger.info("*** new_groups=%r", new_groups)
        for grp in new_groups:
            self.assertIn(self.itb.ou_B.name, grp)
            self.assertNotIn(self.itb.ou_A.name, grp)

    def test_09_move_teacher_remove_primary_with_classes(self):
        self.logger.info(
            "*** Going to create teacher in OUs %r and %r, then remove it from primary (%r). ***",
            self.itb.ou_A.name,
            self.itb.ou_B.name,
            self.itb.ou_A.name,
        )
        self.logger.info("*** Using OUs %r and %r.", self.itb.ou_A.name, self.itb.ou_B.name)
        create_attrs = self.make_user_attrs(
            [self.itb.ou_A.name, self.itb.ou_B.name], partial=False, roles=("teacher",)
        )
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.assertEqual(create_attrs["school"].strip("/").split("/")[-1], self.itb.ou_A.name)
        self.assertEqual(
            [
                create_attrs["schools"][0].strip("/").split("/")[-1],
                create_attrs["schools"][1].strip("/").split("/")[-1],
            ],
            [self.itb.ou_A.name, self.itb.ou_B.name],
        )
        self.assertSetEqual(
            set(create_attrs["school_classes"].keys()), {self.itb.ou_A.name, self.itb.ou_B.name}
        )
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(create_attrs)
        )

        create_result = create_remote_static((self.auth_headers, create_attrs))
        self.logger.debug("*** create_result=%r", create_result)
        self.assertEqual(create_result["name"], create_attrs["name"])
        self.assertEqual(create_result["school"], create_attrs["school"])
        self.assertSetEqual(set(create_result["schools"]), set(create_attrs["schools"]))
        self.assertDictEqual(create_result["school_classes"], create_attrs["school_classes"])

        user_old = self.get_import_user(create_result["dn"])
        self.logger.debug("*** user_old.school_classes=%r", user_old.school_classes)
        user_old_udm = user_old.get_udm_object(self.lo)
        old_groups = user_old_udm["groups"]
        self.logger.info("*** old_groups=%r", old_groups)
        for grp_name in (
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_B.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_B.name),
        ):
            assert any(dn.startswith(grp_name) for dn in old_groups)

        create_attrs_school_classes = dict(
            (ou, ["{}-{}".format(ou, k) for k in kls])
            for ou, kls in create_attrs["school_classes"].items()
        )
        self.logger.info("*** user_old.school_classes    =%r", user_old.school_classes)
        self.logger.info("*** create_attrs_school_classes=%r", create_attrs_school_classes)
        self.assertDictEqual(user_old.school_classes, create_attrs_school_classes)

        modify_attrs = {
            "school": create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name),
            "schools": [create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name)],
        }
        self.logger.info("*** modify_attrs=%r", modify_attrs)
        self.logger.debug("*** zzz...")
        time.sleep(5)

        resource_new = partial_update_remote_static(
            (self.auth_headers, create_result["name"], modify_attrs)
        )
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(create_result["name"], resource_new["name"])
        self.assertDictEqual(
            resource_new["school_classes"],
            {self.itb.ou_B.name: create_attrs["school_classes"][self.itb.ou_B.name]},
        )
        self.logger.debug("*** zzz...")
        time.sleep(5)

        user = self.get_import_user(resource_new["dn"])
        self.logger.debug("*** user.school_classes=%r", user.school_classes)
        self.assertDictEqual(
            user.school_classes,
            {
                self.itb.ou_B.name: [
                    "{}-{}".format(self.itb.ou_B.name, k)
                    for k in create_attrs["school_classes"][self.itb.ou_B.name]
                ]
            },
        )
        self.assertEqual(create_result["name"], user.name)
        url = urljoin(RESSOURCE_URLS["users"], create_result["name"] + "/")
        self.assertEqual(resource_new["url"], url)

        resource_new2 = api_call("get", url, headers=self.auth_headers)
        self.assertDictEqual(resource_new, resource_new2)

        self.compare_import_user_and_resource(user, resource_new)
        self.logger.info("*** OK: LDAP <-> resource")

        user_new_udm = user.get_udm_object(self.lo)
        new_groups = user_new_udm["groups"]
        self.logger.info("*** new_groups=%r", new_groups)
        for grp in new_groups:
            self.assertIn(self.itb.ou_B.name, grp)
            self.assertNotIn(self.itb.ou_A.name, grp)

    def test_10_move_teacher_remove_primary_no_classes_in_new_school(self):
        self.logger.info(
            "*** Going to create teacher in OUs %r and %r, then remove it from primary (%r). ***",
            self.itb.ou_A.name,
            self.itb.ou_B.name,
            self.itb.ou_A.name,
        )
        self.logger.info("*** Using OUs %r and %r.", self.itb.ou_A.name, self.itb.ou_B.name)
        create_attrs = self.make_user_attrs(
            [self.itb.ou_A.name, self.itb.ou_B.name], partial=False, roles=("teacher",)
        )
        del create_attrs["school_classes"][self.itb.ou_B.name]
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.assertEqual(create_attrs["school"].strip("/").split("/")[-1], self.itb.ou_A.name)
        self.assertEqual(
            [
                create_attrs["schools"][0].strip("/").split("/")[-1],
                create_attrs["schools"][1].strip("/").split("/")[-1],
            ],
            [self.itb.ou_A.name, self.itb.ou_B.name],
        )
        self.assertListEqual(create_attrs["school_classes"].keys(), [self.itb.ou_A.name])
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(create_attrs)
        )

        create_result = create_remote_static((self.auth_headers, create_attrs))
        self.logger.debug("*** create_result=%r", create_result)
        self.assertEqual(create_result["name"], create_attrs["name"])
        self.assertEqual(create_result["school"], create_attrs["school"])
        self.assertSetEqual(set(create_result["schools"]), set(create_attrs["schools"]))
        self.assertDictEqual(create_result["school_classes"], create_attrs["school_classes"])

        user_old = self.get_import_user(create_result["dn"])
        self.logger.debug("*** user_old.school_classes=%r", user_old.school_classes)
        user_old_udm = user_old.get_udm_object(self.lo)
        old_groups = user_old_udm["groups"]
        self.logger.info("*** old_groups=%r", old_groups)
        for grp_name in (
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_B.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_B.name),
        ):
            assert any(dn.startswith(grp_name) for dn in old_groups)

        create_attrs_school_classes = dict(
            (ou, ["{}-{}".format(ou, k) for k in kls])
            for ou, kls in create_attrs["school_classes"].items()
        )
        self.logger.info("*** user_old.school_classes    =%r", user_old.school_classes)
        self.logger.info("*** create_attrs_school_classes=%r", create_attrs_school_classes)
        self.assertDictEqual(user_old.school_classes, create_attrs_school_classes)

        modify_attrs = {
            "school": create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name),
            "schools": [create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name)],
        }
        self.logger.info("*** modify_attrs=%r", modify_attrs)
        self.logger.debug("*** zzz...")
        time.sleep(5)

        resource_new = partial_update_remote_static(
            (self.auth_headers, create_result["name"], modify_attrs)
        )
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(create_result["name"], resource_new["name"])
        self.assertEqual(resource_new["school_classes"], {})
        self.logger.debug("*** zzz...")
        time.sleep(5)

        user = self.get_import_user(resource_new["dn"])
        self.logger.debug("*** user.school_classes=%r", user.school_classes)
        self.assertEqual(user.school_classes, {})
        self.assertEqual(create_result["name"], user.name)
        url = urljoin(RESSOURCE_URLS["users"], create_result["name"] + "/")
        self.assertEqual(resource_new["url"], url)

        resource_new2 = api_call("get", url, headers=self.auth_headers)
        self.assertDictEqual(resource_new, resource_new2)

        self.compare_import_user_and_resource(user, resource_new)
        self.logger.info("*** OK: LDAP <-> resource")

        user_new_udm = user.get_udm_object(self.lo)
        new_groups = user_new_udm["groups"]
        self.logger.info("*** new_groups=%r", new_groups)
        for grp in new_groups:
            self.assertIn(self.itb.ou_B.name, grp)
            self.assertNotIn(self.itb.ou_A.name, grp)

    def test_11_move_teacher_remove_primary_with_classes_and_rename(self):
        self.logger.info(
            "*** Going to create teacher in OUs %r and %r, then remove it from primary (%r) and rename "
            "it. ***",
            self.itb.ou_A.name,
            self.itb.ou_B.name,
            self.itb.ou_A.name,
        )
        self.logger.info("*** Using OUs %r and %r.", self.itb.ou_A.name, self.itb.ou_B.name)
        create_attrs = self.make_user_attrs(
            [self.itb.ou_A.name, self.itb.ou_B.name], partial=False, roles=("teacher",)
        )
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.assertEqual(create_attrs["school"].strip("/").split("/")[-1], self.itb.ou_A.name)
        self.assertEqual(
            [
                create_attrs["schools"][0].strip("/").split("/")[-1],
                create_attrs["schools"][1].strip("/").split("/")[-1],
            ],
            [self.itb.ou_A.name, self.itb.ou_B.name],
        )
        self.assertSetEqual(
            set(create_attrs["school_classes"].keys()), {self.itb.ou_A.name, self.itb.ou_B.name}
        )
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(create_attrs)
        )

        create_result = create_remote_static((self.auth_headers, create_attrs))
        self.logger.debug("*** create_result=%r", create_result)
        self.assertEqual(create_result["name"], create_attrs["name"])
        self.assertEqual(create_result["school"], create_attrs["school"])
        self.assertSetEqual(set(create_result["schools"]), set(create_attrs["schools"]))
        self.assertDictEqual(create_result["school_classes"], create_attrs["school_classes"])

        user_old = self.get_import_user(create_result["dn"])
        self.logger.debug("*** user_old.school_classes=%r", user_old.school_classes)
        user_old_udm = user_old.get_udm_object(self.lo)
        old_groups = user_old_udm["groups"]
        self.logger.info("*** old_groups=%r", old_groups)
        for grp_name in (
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_B.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_B.name),
        ):
            assert any(dn.startswith(grp_name) for dn in old_groups)

        create_attrs_school_classes = dict(
            (ou, ["{}-{}".format(ou, k) for k in kls])
            for ou, kls in create_attrs["school_classes"].items()
        )
        self.logger.info("*** user_old.school_classes    =%r", user_old.school_classes)
        self.logger.info("*** create_attrs_school_classes=%r", create_attrs_school_classes)
        self.assertDictEqual(user_old.school_classes, create_attrs_school_classes)

        modify_attrs = {
            "name": uts.random_username(),
            "school": create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name),
            "schools": [create_result["school"].replace(self.itb.ou_A.name, self.itb.ou_B.name)],
        }
        self.assertNotEqual(user_old.name, modify_attrs["name"])
        self.logger.info("*** modify_attrs=%r", modify_attrs)
        self.logger.debug("*** zzz...")
        time.sleep(5)

        resource_new = partial_update_remote_static(
            (self.auth_headers, create_result["name"], modify_attrs)
        )
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(modify_attrs["name"], resource_new["name"])
        self.assertDictEqual(
            resource_new["school_classes"],
            {self.itb.ou_B.name: create_attrs["school_classes"][self.itb.ou_B.name]},
        )
        self.logger.debug("*** zzz...")
        time.sleep(5)

        user = self.get_import_user(resource_new["dn"])
        self.logger.debug("*** user.school_classes=%r", user.school_classes)
        self.assertDictEqual(
            user.school_classes,
            {
                self.itb.ou_B.name: [
                    "{}-{}".format(self.itb.ou_B.name, k)
                    for k in create_attrs["school_classes"][self.itb.ou_B.name]
                ]
            },
        )
        self.assertEqual(modify_attrs["name"], user.name)
        url = urljoin(RESSOURCE_URLS["users"], modify_attrs["name"] + "/")
        self.assertEqual(resource_new["url"], url)

        resource_new2 = api_call("get", url, headers=self.auth_headers)
        self.assertDictEqual(resource_new, resource_new2)

        self.compare_import_user_and_resource(user, resource_new)
        self.logger.info("*** OK: LDAP <-> resource")

        user_new_udm = user.get_udm_object(self.lo)
        new_groups = user_new_udm["groups"]
        self.logger.info("*** new_groups=%r", new_groups)
        for grp in new_groups:
            self.assertIn(self.itb.ou_B.name, grp)
            self.assertNotIn(self.itb.ou_A.name, grp)

    def test_12_modify_teacher_remove_all_classes(self):
        self.logger.info(
            "*** Going to create teacher in OUs %r, then remove all its classes. ***", self.itb.ou_A.name
        )
        self.logger.info("*** Using OUs %r.", self.itb.ou_A.name)
        create_attrs = self.make_user_attrs([self.itb.ou_A.name], partial=False, roles=("teacher",))
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.assertListEqual(create_attrs["school_classes"].keys(), [self.itb.ou_A.name])
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(create_attrs)
        )

        create_result = create_remote_static((self.auth_headers, create_attrs))
        self.logger.debug("*** create_result=%r", create_result)
        self.assertEqual(create_result["name"], create_attrs["name"])
        self.assertEqual(create_result["school"], create_attrs["school"])
        self.assertSetEqual(set(create_result["schools"]), set(create_attrs["schools"]))
        self.assertDictEqual(create_result["school_classes"], create_attrs["school_classes"])

        user_old = self.get_import_user(create_result["dn"])
        self.logger.debug("*** user_old.school_classes=%r", user_old.school_classes)
        user_old_udm = user_old.get_udm_object(self.lo)
        old_groups = user_old_udm["groups"]
        self.logger.info("*** old_groups=%r", old_groups)
        for grp_name in (
            "cn=lehrer-{0},cn=groups,ou={0},".format(self.itb.ou_A.name),
            "cn=Domain Users {0},cn=groups,ou={0},".format(self.itb.ou_A.name),
        ):
            assert any(dn.startswith(grp_name) for dn in old_groups)

        create_attrs_school_classes = dict(
            (ou, ["{}-{}".format(ou, k) for k in kls])
            for ou, kls in create_attrs["school_classes"].items()
        )
        self.logger.info("*** user_old.school_classes    =%r", user_old.school_classes)
        self.logger.info("*** create_attrs_school_classes=%r", create_attrs_school_classes)
        self.assertDictEqual(user_old.school_classes, create_attrs_school_classes)

        modify_attrs = {
            "school_classes": {},
        }
        self.logger.info("*** modify_attrs=%r", modify_attrs)
        self.logger.debug("*** zzz...")
        time.sleep(5)

        resource_new = partial_update_remote_static(
            (self.auth_headers, create_result["name"], modify_attrs)
        )
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(create_result["name"], resource_new["name"])
        self.assertEqual(resource_new["school_classes"], {})
        self.logger.debug("*** zzz...")
        time.sleep(5)

        user = self.get_import_user(resource_new["dn"])
        self.logger.debug("*** user.school_classes=%r", user.school_classes)
        self.assertEqual(user.school_classes, {})
        self.assertEqual(create_result["name"], user.name)
        url = urljoin(RESSOURCE_URLS["users"], create_result["name"] + "/")
        self.assertEqual(resource_new["url"], url)

        resource_new2 = api_call("get", url, headers=self.auth_headers)
        self.assertDictEqual(resource_new, resource_new2)

        self.compare_import_user_and_resource(user, resource_new)
        self.logger.info("*** OK: LDAP <-> resource")

    def test_13_modify_classes_2old_2new(self):
        role = random.choice(("student", "teacher"))
        self.logger.info("*** Going to create %s in OUs %r. ***", role, self.itb.ou_A.name)
        self.logger.info("*** Using OUs %r.", self.itb.ou_A.name)
        create_attrs = self.make_user_attrs([self.itb.ou_A.name], partial=False, roles=(role,))
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.assertListEqual(create_attrs["school_classes"].keys(), [self.itb.ou_A.name])
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(create_attrs)
        )

        create_result = create_remote_static((self.auth_headers, create_attrs))
        self.logger.debug("*** create_result=%r", create_result)
        self.assertEqual(create_result["name"], create_attrs["name"])
        self.assertEqual(create_result["school"], create_attrs["school"])
        self.assertSetEqual(set(create_result["schools"]), set(create_attrs["schools"]))
        self.assertDictEqual(create_result["school_classes"], create_attrs["school_classes"])

        user_old = self.get_import_user(create_result["dn"])
        old_school_classes = user_old.school_classes
        self.logger.debug("*** old_school_classes=%r", old_school_classes)

        new_school_classes = dict(
            (ou, sorted([uts.random_username(4), uts.random_username(4)]))
            for ou in old_school_classes.keys()
        )
        self.logger.debug("*** new_school_classes=%r", new_school_classes)
        modify_attrs = {
            "school_classes": new_school_classes,
        }
        self.logger.info("*** modify_attrs=%r", modify_attrs)
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(modify_attrs)
        )
        resource_new = partial_update_remote_static(
            (self.auth_headers, create_result["name"], modify_attrs)
        )
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(create_result["name"], resource_new["name"])
        self.assertDictEqual(resource_new["school_classes"], new_school_classes)

        user = self.get_import_user(resource_new["dn"])
        self.assertEqual(create_result["name"], user.name)
        self.logger.debug("*** user.school_classes=%r", user.school_classes)
        classes_without_ous = dict(
            (ou, [k.split("-", 1)[1] for k in kls]) for ou, kls in user.school_classes.items()
        )
        self.logger.debug("*** user.school_classes without ous=%r", classes_without_ous)
        self.assertDictEqual(classes_without_ous, new_school_classes)
        self.logger.info("*** OK: 2 classes in old and 2 changed classes in new")

    def test_14_modify_classes_0old_2new(self):
        role = random.choice(("student", "teacher"))
        self.logger.info("*** Going to create %s in OUs %r. ***", role, self.itb.ou_A.name)
        self.logger.info("*** Using OUs %r.", self.itb.ou_A.name)
        create_attrs = self.make_user_attrs(
            [self.itb.ou_A.name], partial=False, roles=(role,), school_classes={}
        )
        self.logger.info("*** create_attrs=%r", create_attrs)
        self.assertDictEqual(create_attrs["school_classes"], {})

        create_result = create_remote_static((self.auth_headers, create_attrs))
        self.logger.debug("*** create_result=%r", create_result)
        self.assertEqual(create_result["name"], create_attrs["name"])
        self.assertEqual(create_result["school"], create_attrs["school"])
        self.assertSetEqual(set(create_result["schools"]), set(create_attrs["schools"]))
        self.assertDictEqual(create_result["school_classes"], {})

        user_old = self.get_import_user(create_result["dn"])
        old_school_classes = user_old.school_classes
        self.logger.debug("*** old_school_classes=%r", old_school_classes)
        self.assertDictEqual(old_school_classes, {})

        new_school_classes = dict(
            (ou, sorted([uts.random_username(4), uts.random_username(4)]))
            for ou in old_school_classes.keys()
        )
        self.logger.debug("*** new_school_classes=%r", new_school_classes)
        modify_attrs = {
            "school_classes": new_school_classes,
        }
        self.logger.info("*** modify_attrs=%r", modify_attrs)
        self.schoolenv.udm._cleanup.setdefault("groups/group", []).extend(
            self.extract_class_dns(modify_attrs)
        )
        resource_new = partial_update_remote_static(
            (self.auth_headers, create_result["name"], modify_attrs)
        )
        self.logger.info("*** API call (modify) returned: %r", resource_new)
        self.assertEqual(create_result["name"], resource_new["name"])
        self.assertDictEqual(resource_new["school_classes"], new_school_classes)

        user = self.get_import_user(resource_new["dn"])
        self.assertEqual(create_result["name"], user.name)
        self.logger.debug("*** user.school_classes=%r", user.school_classes)
        classes_without_ous = dict(
            (ou, [k.split("-", 1)[1] for k in kls]) for ou, kls in user.school_classes.items()
        )
        self.logger.debug("*** user.school_classes without ous=%r", classes_without_ous)
        self.assertDictEqual(classes_without_ous, new_school_classes)
        self.logger.info("*** OK: 0 classes in old and 2 classes in new")


if __name__ == "__main__":
    main(verbosity=2)
