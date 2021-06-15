#!/usr/share/ucs-test/runner python3
# coding=utf-8
## desc: ucs-school-lessontimes-module
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: careful
## packages: [ucs-school-umc-lessontimes]

import univention.testing.utils as utils
from univention.testing.umc import Client


def getLessons(connection):
    return connection.umc_command("lessontimes/get").result


def addLesson(connection, name, begin, end):
    lesson = [name, begin, end]
    lessonsList = getLessons(connection)
    lessonsList.append(lesson)
    return connection.umc_command("lessontimes/set", {"lessons": lessonsList}).result


def delLesson(connection, name, begin, end):
    lessonsList = getLessons(connection)
    for item in lessonsList:
        if name in item:
            lessonsList.remove(item)
    param = {"lessons": lessonsList}
    return connection.umc_command("lessontimes/set", param).result


def main():
    connection = Client.get_test_connection(language="en-US")
    connection.umc_set({"locale": "en_US"})

    # 1 adding a lesson
    addLesson(connection, "99. Stunde", "00:00", "0:05")

    # 2 checking time format
    obj = addLesson(connection, "98. Stunde", "40", "80")["message"]
    if "invalid time format" not in obj:
        utils.fail("invalid time format is not detected: %s" % obj)

    # 3 check overlapping in time
    eng = "Overlapping lessons are not allowed"
    obj = addLesson(connection, "98. Stunde", "00:03", "0:06")["message"]
    if eng not in obj:
        utils.fail("Overlapping lessons time is not detected: %s" % obj)

    # 4 check overlapping in names
    obj = addLesson(connection, "99. Stunde", "00:06", "0:08")["message"]
    if eng not in obj:
        utils.fail("Overlapping lessons names is not detected: %s" % obj)

    # 5 removing a lesson
    delLesson(connection, "99. Stunde", "00:00", "1:00")


if __name__ == "__main__":
    main()
