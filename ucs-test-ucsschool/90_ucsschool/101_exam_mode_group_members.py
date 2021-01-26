#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Simple exam group memberUid & uniqueMember check
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## bugs: [36251, 41568]
## packages: [univention-samba4, ucs-school-umc-computerroom, ucs-school-umc-exam]

from datetime import datetime, timedelta

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.udm
import univention.testing.utils as utils
from ucsschool.lib.models import Student
from univention.testing.ucsschool.computerroom import Computers, Room
from univention.testing.ucsschool.exam import Exam
from univention.uldap import getMachineConnection


def main():
    with univention.testing.udm.UCSTestUDM() as udm:
        with utu.UCSTestSchool() as schoolenv:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                open_ldap_co = schoolenv.open_ldap_connection()
                ucr.load()

                if ucr.is_true("ucsschool/singlemaster"):
                    edudc = None
                else:
                    edudc = ucr.get("hostname")
                school, oudn = schoolenv.create_ou(name_edudc=edudc)
                klasse_dn = udm.create_object(
                    "groups/group",
                    name="%s-AA1" % school,
                    position="cn=klassen,cn=schueler,cn=groups,%s" % oudn,
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
                student2.create(open_ldap_co)
                udm.modify_object("groups/group", dn=klasse_dn, append={"users": [teadn]})
                udm.modify_object("groups/group", dn=klasse_dn, append={"users": [studn]})
                udm.modify_object("groups/group", dn=klasse_dn, append={"users": [student2.dn]})

                # import random computers
                computers = Computers(open_ldap_co, school, 3, 0, 0)
                pc1, pc2, pc3 = computers.create()

                # set 2 computer rooms to contain the created computers
                room1 = Room(school, host_members=pc1.dn)
                room2 = Room(school, host_members=[pc2.dn, pc3.dn], teacher_computers=[pc2.dn])
                for room in [room1, room2]:
                    schoolenv.create_computerroom(
                        school,
                        name=room.name,
                        description=room.description,
                        host_members=room.host_members,
                        teacher_computers=room.teacher_computers,
                    )

                # Set an exam and start it
                current_time = datetime.now()
                chosen_time = current_time + timedelta(hours=2)
                exam = Exam(
                    school=school,
                    room=room2.dn,  # room dn
                    examEndTime=chosen_time.strftime("%H:%M"),  # in format "HH:mm"
                    recipients=[klasse_dn],  # list of classes dns
                )
                exam.start()

                try:
                    expected_memberUid = ["%s$" % pc3.name, "exam-%s" % stu, "exam-%s" % student2.name]
                    expected_uniqueMember = [
                        "%s" % pc3.dn,
                        "uid=exam-%s,cn=examusers,%s" % (stu, oudn),
                        "uid=exam-%s,cn=examusers,%s" % (student2.name, oudn),
                    ]

                    # Get the current attributes values
                    lo = getMachineConnection()
                    exam_group_dn = "cn=OU%s-Klassenarbeit,cn=ucsschool,cn=groups,%s" % (
                        school,
                        ucr.get("ldap/base"),
                    )
                    memberUid = lo.search(base=exam_group_dn)[0][1].get("memberUid")
                    uniqueMember = lo.search(base=exam_group_dn)[0][1].get("uniqueMember")

                    if set(memberUid) != set(expected_memberUid):
                        utils.fail(
                            "Current memberUid = %r\nExpected = %r" % (memberUid, expected_memberUid)
                        )
                    if set(uniqueMember) != set(expected_uniqueMember):
                        utils.fail(
                            "Current uniqueMember = %r\nExpected= %r"
                            % (uniqueMember, expected_uniqueMember)
                        )

                finally:
                    exam.finish()
                    student2.remove(open_ldap_co)


if __name__ == "__main__":
    main()
