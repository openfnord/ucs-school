#!/usr/share/ucs-test/runner python3
## desc: ucs-school-printermoderator-module-check
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages:  [ucs-school-umc-printermoderation, ucs-school-import]

from __future__ import print_function

import os
import socket
import subprocess
import tempfile
import time
from mimetypes import MimeTypes

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.udm
import univention.testing.utils as utils
from univention.testing.umc import Client


def _dir(userName):
    path = "/var/spool/cups-pdf/%s" % (userName)
    files = []
    for root, _, filenames in os.walk(path):
        for f in filenames:
            files.append(os.path.relpath(os.path.join(root, f), path))
    return files


# Order print job for postscript test page and check if it is stored in the
# user spool directory
def orderPrint(printer, userName, _file):
    with ucr_test.UCSTestConfigRegistry() as ucr:
        master = ucr.get("ldap/master").split(".", 1)[0]
    oldPrintJobs = _dir(userName)
    job = []
    cmds = [
        ["lpr", "-P", printer, "-U", userName, _file],
        [
            "smbclient",
            "//%s/%s" % (master, printer),
            "-d3",
            "-U",
            "%s%%%s" % (userName, "univention"),
            "-c",
            "print %s" % _file,
        ],
    ]
    # cmd = ['smbclient', "-N", "-L", "//%s/%s" % (master, printer)]
    for cmd in cmds:
        print("cmd = %s" % " ".join(cmd))
        err, out = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        # workaround for smbclient session setup failed: NT_STATUS_LOGON_FAILURE
        for waitingTime in range(150):
            err, out = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ).communicate()
            if err:
                time.sleep(1)
                print(" - %d - " % waitingTime, err, end=" ")
            else:
                break
        err, out = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if err:
            utils.fail("Orderprint failure:\n%r\n%r" % (err, out))
        if "smbclient" in cmd:
            userName = userName.lower()
        for waitingTime in range(60):
            job = [x for x in _dir(userName) if x not in oldPrintJobs]
            if not job:
                time.sleep(1)
                print(" - %d - " % waitingTime, "Waiting for print job .. ")
            else:
                break
        if not job:
            utils.fail("Ordered print job was not stored in user spool directory")


# add / del / modify Printer
def doPrinter(operation, printer_name, school, spool_host, domainname):
    localIp = socket.gethostbyname(socket.gethostname())
    uri = "%s://%s" % ("lpd", localIp)
    print_server = "%s.%s" % (spool_host, domainname)
    f = tempfile.NamedTemporaryFile("w+", suffix=".csv")
    line = "%s\t%s\t%s\t%s\t%s\n" % (operation, school, print_server, printer_name, uri)
    f.write(line)
    f.flush()
    cmd = ["/usr/share/ucs-school-import/scripts/import_printer", f.name]
    retval = subprocess.call(cmd)
    f.close()
    if retval:
        utils.fail("Unexpected error while acting on Printer")
    utils.wait_for_replication_and_postrun()


# check the existance of the created printer
def printerExist(connection, printerName, school):
    requestResult = connection.umc_command("printermoderation/printers", {"school": school}).result
    return any(d for d in requestResult if d["label"] == printerName)


# get the current printed jobs
def queryPrintJobs(connection, printerName, cName, school, pattern, basedn):
    if cName != "None":
        cdn = "cn=%s,cn=klassen,cn=schueler,cn=groups,ou=%s,%s" % (cName, school, basedn)
    else:
        cdn = cName
    param = {"school": school, "class": cdn, "pattern": pattern}
    return connection.umc_command("printermoderation/query", param).result


# delete a specific printjob
def delPrintJob(connection, userName, printJob):
    param = {"username": userName, "printjob": printJob}
    if not connection.umc_command("printermoderation/delete", param).result:
        utils.fail("Could not delete print jobs")


# Check the file type of the printed pdf
def checkPrintJobs(printJobs):
    if not printJobs:
        utils.fail("No print job was found")
    mime = MimeTypes()
    for job in printJobs:
        mime_type, _ = mime.guess_type(job)
        if "/pdf" not in mime_type:
            utils.fail("Unexpected file type")


# download print jobs
def downloadPrintJobs(client, userName, printJob):
    param = {"username": userName, "printjob": os.path.basename(printJob)}
    response = client.umc_command("printermoderation/download", param, print_response=False)
    assert response.get_header("Content-Type") == "application/pdf"
    assert response.body
    # TODO: validate the content, e.g. with magic()


# get print jobs for a specific user
def getPrintJobs(alljobs, userName):
    return [x["id"] for x in alljobs if x["username"] == userName]


# Accept printjobs and send them to the hard printer
def acceptprint(connection, userName, printJobPath, printerName, spoolHost, domainname):
    printJob = printJobPath.split("/")[-1]
    printerURI = "%s.%s://%s" % (spoolHost, domainname, printerName)
    param = {"username": userName, "printjob": printJob, "printer": printerURI}
    reqResult = connection.umc_command("printermoderation/print", param).result
    print("reqResult = ", reqResult)
    if not reqResult:
        utils.fail("Could not pass print jobs to hard printer")


def main():
    with univention.testing.udm.UCSTestUDM() as udm:
        with utu.UCSTestSchool() as schoolenv:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                newPrinterName = uts.random_string()
                default_printer = "PDFDrucker"
                test_file = "testpage.ps"
                domainname = ucr.get("domainname")
                basedn = ucr.get("ldap/base")
                host = ucr.get("hostname")
                if ucr.is_true("ucsschool/singlemaster"):
                    edudc = None
                else:
                    edudc = host
                school, oudn = schoolenv.create_ou(name_edudc=edudc)
                klasse1_dn = udm.create_object(
                    "groups/group",
                    name="%s-1A" % school,
                    position="cn=klassen,cn=schueler,cn=groups,%s" % oudn,
                )
                klasse2_dn = udm.create_object(
                    "groups/group",
                    name="%s-2B" % school,
                    position="cn=klassen,cn=schueler,cn=groups,%s" % oudn,
                )
                tea, teadn = schoolenv.create_user(school, is_teacher=True)
                stu1, stu1_dn = schoolenv.create_user(school)
                stu2, stu2_dn = schoolenv.create_user(school)

                name = "%s%s" % (uts.random_name(2).upper(), uts.random_name(8))
                stu3, stu3_dn = schoolenv.create_user(school, username=name)
                stu4, stu4_dn = schoolenv.create_user(school, username="%s2" % name)

                udm.modify_object("groups/group", dn=klasse1_dn, append={"users": [teadn]})
                udm.modify_object("groups/group", dn=klasse1_dn, append={"users": [stu1_dn]})
                udm.modify_object("groups/group", dn=klasse1_dn, append={"users": [stu3_dn]})

                udm.modify_object("groups/group", dn=klasse2_dn, append={"users": [stu2_dn]})
                udm.modify_object("groups/group", dn=klasse2_dn, append={"users": [stu4_dn]})

                utils.wait_for_replication_and_postrun()

                connection = Client(host)
                connection.authenticate(tea, "univention")

                # add new printer
                doPrinter("A", newPrinterName, school, host, domainname)

                # check if the printer exists
                if not printerExist(connection, newPrinterName, school):
                    utils.fail("Printer not found")

                # order print jobs
                for stu in (stu1, stu2, stu3, stu4):
                    orderPrint(default_printer, stu, test_file)

                # query all orderd print jobs
                alljobs = queryPrintJobs(connection, newPrinterName, "None", school, "", basedn)
                # query all orderd print jobs from classes 1A
                alljobs1A = queryPrintJobs(
                    connection, newPrinterName, "%s-1A" % school, school, "", basedn
                )
                alljobs2B = queryPrintJobs(  # noqa: F841  # TODO: check value?
                    connection, newPrinterName, "%s-2B" % school, school, "", basedn
                )

                if alljobs1A == alljobs:
                    utils.fail("Unexpected job query result")

                # get print jobs
                printJobs = {}
                for stu in (stu1, stu2, stu3, stu4):
                    printJobs.update({stu: getPrintJobs(alljobs, stu)})

                # check file type for the printjobs files
                for stu in printJobs:
                    checkPrintJobs(printJobs.get(stu))

                for stu in (stu1, stu3):
                    # download print jobs for stu and check the filetype
                    downloadPrintJobs(connection, stu, printJobs.get(stu)[0])

                    # accepting a print job from stu
                    acceptprint(connection, stu, printJobs.get(stu)[0], newPrinterName, host, domainname)

                    # delete a print job for stu 1
                    delPrintJob(connection, stu, printJobs.get(stu)[0])

                # delete a print job for stu 2
                delPrintJob(connection, stu2, printJobs.get(stu2)[0])

                # delete the created printer
                doPrinter("D", newPrinterName, school, host, domainname)


if __name__ == "__main__":
    main()
