#!/usr/share/ucs-test/runner pytest -s -l -v
# -*- coding: utf-8 -*-
## desc: Check the teacher assignment umc module
## exposure: dangerous
## tags: [apptest, ucsschool]
## bugs: [50008]


import pytest

import univention.testing.strings as uts
from ucsschool.lib.models.group import SchoolClass
from ucsschool.lib.models.user import User
from univention.testing.ucsschool.ucs_test_school import UCSTestSchool
from univention.testing.umc import Client
from univention.testing.utils import wait_for_listener_replication


@pytest.fixture(scope="module")
def schoolenv():
    with UCSTestSchool() as schoolenv:
        hostname = schoolenv.ucr["hostname"]
        schoolenv.schools = schoolenv.create_multiple_ous(2, name_edudc=hostname)
        schoolenv.teachers = {}
        for school, school_dn in schoolenv.schools:
            school_class, _ = schoolenv.create_school_class(school, uts.random_string())
            _, schoolenv.teachers[school] = schoolenv.create_teacher(
                school, classes=school_class, schools=[s[0] for s in schoolenv.schools]
            )
        yield schoolenv


class ChangeTeachersError(Exception):
    pass


class TestSchoolTeacherAssignmentDomainAdmin(object):
    @pytest.fixture(scope="class")
    def client(self):
        return Client.get_test_connection()

    def __school_class_teachers(self, schoolClass):
        return [
            t
            for t in schoolClass.users
            if User.from_dn(t, schoolClass.school, self.schoolenv.lo).is_teacher(self.schoolenv.lo)
        ]

    def __test_teacher_assignment(self, new_teachers):
        school = self.schoolenv.schools[0][0]
        school_class, school_class_dn = self.schoolenv.create_school_class(school, uts.random_string())
        self.schoolenv.create_teacher(school, classes=school_class)
        schoolClass = SchoolClass.from_dn(school_class_dn, school, self.schoolenv.lo)
        original_teachers = self.__school_class_teachers(schoolClass)
        visible_teachers = [
            t["id"]
            for t in self.client.umc_command(
                "schoolgroups/get", flavor="class", options=[school_class_dn]
            ).result[0]["members"]
        ]
        result = self.client.umc_command(
            "schoolgroups/put",
            flavor="class",
            options=[{"object": {"$dn$": school_class_dn, "members": visible_teachers + new_teachers}}],
        )
        wait_for_listener_replication()
        if result.result is False:
            raise ChangeTeachersError
        schoolClass = SchoolClass.from_dn(school_class_dn, school, self.schoolenv.lo)
        assert set(self.__school_class_teachers(schoolClass)) == set(original_teachers + new_teachers)
        self.client.umc_command(
            "schoolgroups/put",
            flavor="class",
            options=[{"object": {"$dn$": school_class_dn, "members": visible_teachers}}],
        )
        wait_for_listener_replication()
        schoolClass = SchoolClass.from_dn(school_class_dn, school, self.schoolenv.lo)
        assert set(self.__school_class_teachers(schoolClass)) == set(original_teachers)

    def test_teacher_from_primary_school(self, schoolenv, client):
        schools = schoolenv.schools
        self.schoolenv = schoolenv
        self.client = client
        self.__test_teacher_assignment([schoolenv.teachers[schools[0][0]]])

    def test_teacher_from_secondary_school(self, schoolenv, client):
        schools = schoolenv.schools
        self.schoolenv = schoolenv
        self.client = client
        self.__test_teacher_assignment([schoolenv.teachers[schools[1][0]]])

    def test_teachers_from_two_schools(self, schoolenv, client):
        schools = schoolenv.schools
        self.schoolenv = schoolenv
        self.client = client
        self.__test_teacher_assignment(
            [schoolenv.teachers[schools[0][0]], schoolenv.teachers[schools[1][0]]]
        )


class TestSchoolTeacherAssignmentSchoolAdmin(TestSchoolTeacherAssignmentDomainAdmin):
    @pytest.fixture(scope="class")
    def client(self, schoolenv):
        schools = schoolenv.schools
        school_admin, school_admin_dn = schoolenv.create_school_admin(
            schools[0][0], is_teacher=True, is_staff=False
        )
        return Client(username=school_admin, password="univention")


class TestSchoolTeacherAssignmentSchoolAdminSecondary(TestSchoolTeacherAssignmentDomainAdmin):
    @pytest.fixture(scope="class")
    def client(self, schoolenv):
        schools = schoolenv.schools
        school_admin, school_admin_dn = schoolenv.create_school_admin(
            schools[1][0], is_teacher=True, is_staff=False, schools=[schools[0][0], schools[1][0]]
        )
        return Client(username=school_admin, password="univention")
