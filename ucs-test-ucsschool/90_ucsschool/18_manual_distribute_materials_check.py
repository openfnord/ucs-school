#!/usr/share/ucs-test/runner python3
## desc: manual_distribute_materials_check
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave, memberserver]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-distribution]

import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.ucsschool.distribution import Distribution
from univention.testing.ucsschool.workgroup import Workgroup
from univention.testing.umc import Client

# Generate the required time variables in the correct format


def getDateTime(starttime, deadline):
    distTime = time.strftime("%H:%M", starttime)
    distDate = time.strftime("%Y-%m-%d", starttime)
    collTime = time.strftime("%H:%M", deadline)
    collDate = time.strftime("%Y-%m-%d", deadline)
    return distTime, distDate, collTime, collDate


def main():
    with utu.UCSTestSchool() as schoolenv:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            host = ucr.get("hostname")
            connection = Client(host)

            # Create ou, teacher, student, group
            school, oudn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))
            tea, teadn = schoolenv.create_user(school, is_teacher=True)
            tea2, teadn2 = schoolenv.create_user(school, is_teacher=True)
            stu, studn = schoolenv.create_user(school)
            group = Workgroup(school, members=[studn])
            group.create()
            utils.wait_for_replication_and_postrun()

            filename = uts.random_string()
            connection.authenticate(tea, "univention")

            # Create new project
            project = Distribution(
                school,
                sender=tea,
                connection=connection,
                ucr=ucr,
                files=[(filename, "utf8")],
                recipients=[group],
                flavor="teacher",
            )
            project.add()
            project.check_add()
            project.distribute()
            project.check_distribute([stu])
            project.collect()
            project.check_collect([stu])

            # Adopting Check
            client2 = Client(host, tea2, "univention")
            filename = uts.random_string()
            # create new project
            project2 = Distribution(
                school,
                sender=tea2,
                connection=client2,
                ucr=ucr,
                files=[(filename, "utf8")],
                recipients=[group],
                flavor="teacher",
            )
            project2.add()
            project.adopt(project2.name)
            project.check_adopt(project2.name)

            # Editing porject check
            MIN_DIST_TIME = 8 * 60
            MIN_COLL_TIME = 18 * 60
            for distType in ["manual", "automatic"]:
                for collType in ["manual", "automatic"]:
                    get = project.get()
                    # change attributes
                    now = time.time()
                    starttime = time.localtime(now + MIN_DIST_TIME)
                    deadline = time.localtime(now + MIN_COLL_TIME)
                    distTime, distDate, collTime, collDate = getDateTime(starttime, deadline)
                    new_description = uts.random_string()
                    new_group = Workgroup(school, members=[studn])
                    new_group.create()
                    project.put(
                        description=new_description,
                        distributeType=distType,
                        distributeTime=distTime,
                        distributeDate=distDate,
                        collectType=collType,
                        collectTime=collTime,
                        collectDate=collDate,
                        recipients=[new_group],
                    )
                    project.check_put(get)
                    MIN_DIST_TIME += 3 * 60
                    MIN_COLL_TIME += 3 * 60

            project.remove()
            project.check_remove()


if __name__ == "__main__":
    main()
