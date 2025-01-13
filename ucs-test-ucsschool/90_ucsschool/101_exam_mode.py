#!/usr/share/ucs-test/runner pytest-3 -s -l -v
## -*- coding: utf-8 -*-
## desc: Exam mode
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1,ucs-school-umc-exam]
## exposure: dangerous
## bugs: [36251, 41568]
## packages: [univention-samba4, ucs-school-umc-computerroom, ucs-school-umc-exam]

from __future__ import print_function

from datetime import datetime, timedelta

import univention.testing.strings as uts
import univention.testing.ucsschool.ucs_test_school as utu
from ucsschool.lib.models.user import Student
from ucsschool.lib.schoolldap import SchoolSearchBase
from univention.testing.ucsschool.computer import Computers
from univention.testing.ucsschool.computerroom import Room
from univention.testing.ucsschool.exam import (
    Exam,
    ExamSaml,
    get_s4_rejected,
    wait_replications_check_rejected_uniqueMember,
)
from univention.testing.udm import UCSTestUDM


class Test_ExamMode(object):
    def __test_exam_mode(self, Exam=Exam):
        with UCSTestUDM() as udm, utu.UCSTestSchool() as schoolenv:
            ucr = schoolenv.ucr
            lo = schoolenv.open_ldap_connection()
            ucr.load()

            print(" ** Initial Status")
            existing_rejects = get_s4_rejected()

            if ucr.is_true("ucsschool/singlemaster"):
                edudc = None
            else:
                edudc = ucr.get("hostname")
            school, oudn = schoolenv.create_ou(name_edudc=edudc)
            search_base = SchoolSearchBase([school])
            klasse_dn = udm.create_object(
                "groups/group", name="%s-AA1" % school, position=search_base.classes
            )

            tea, teadn = schoolenv.create_user(school, is_teacher=True)
            stu, studn = schoolenv.create_user(school)
            student2 = Student(
                name=uts.random_username(),
                school=school,
                firstname=uts.random_name(),
                lastname=uts.random_name(),
            )
            student2.position = "cn=users,%s" % ucr["ldap/base"]
            student2.create(lo)

            udm.modify_object("groups/group", dn=klasse_dn, append={"users": [teadn]})
            udm.modify_object("groups/group", dn=klasse_dn, append={"users": [studn]})
            udm.modify_object("groups/group", dn=klasse_dn, append={"users": [student2.dn]})

            print(" ** After Creating users and classes")
            wait_replications_check_rejected_uniqueMember(existing_rejects)

            # importing random computers
            computers = Computers(lo, school, 2, 0, 0)
            created_computers = computers.create()
            created_computers_dn = computers.get_dns(created_computers)

            # setting 2 computer rooms contain the created computers
            room1 = Room(school, host_members=created_computers_dn[0])
            room2 = Room(school, host_members=created_computers_dn[1])

            # Creating the rooms
            for room in [room1, room2]:
                schoolenv.create_computerroom(
                    school,
                    name=room.name,
                    description=room.description,
                    host_members=room.host_members,
                )

            current_time = datetime.now()
            chosen_time = current_time + timedelta(hours=2)

            print(" ** After creating the rooms")
            wait_replications_check_rejected_uniqueMember(existing_rejects)

            exam = Exam(
                school=school,
                room=room2.dn,  # room dn
                examEndTime=chosen_time.strftime("%H:%M"),  # in format "HH:mm"
                recipients=[klasse_dn],  # list of classes dns
            )

            exam.start()
            print(" ** After starting the exam")
            wait_replications_check_rejected_uniqueMember(existing_rejects)

            exam.finish()
            print(" ** After finishing the exam")
            wait_replications_check_rejected_uniqueMember(existing_rejects)
            student2.remove(lo)

    def test_saml_login(self):
        self.__test_exam_mode(Exam=ExamSaml)

    def test_classic_login(self):
        self.__test_exam_mode()
