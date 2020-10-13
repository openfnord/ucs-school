#!/usr/bin/python2.7
#
# UCS@school join hook
#
# Copyright 2018-2020 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import json
import logging
import optparse
import os
import subprocess
import sys
from collections import namedtuple

try:
    from typing import Any, List, Optional, Union
except ImportError:
    pass

from distutils.version import LooseVersion

from ldap.filter import filter_format

import univention.admin
from univention.config_registry import ConfigRegistry, handler_set
from univention.lib.package_manager import PackageManager

log = None  # type: Optional[logging.Logger]
ucr = None  # type: Optional[ConfigRegistry]

StdoutStderr = namedtuple("StdoutStderr", "stdout stderr")
SchoolMembership = namedtuple("school_membership", "is_edu_school_member is_admin_school_member")


def get_lo(options):  # type: (Any) -> univention.admin.uldap.access
    log.info("Connecting to LDAP as %r ...", options.binddn)
    try:
        lo = univention.admin.uldap.access(
            host=options.master_fqdn,
            port=int(ucr.get("ldap/master/port", "7389")),
            base=ucr.get("ldap/base"),
            binddn=options.binddn,
            bindpw=options.bindpw,
        )
    except univention.admin.uexceptions.authFail:
        log.error("username or password is incorrect")
        sys.exit(5)
    return lo


def get_school_membership(options):  # type: (Any) -> SchoolMembership
    filter_s = filter_format(
        "(&(objectClass=univentionGroup)(uniqueMember=%s))", (ucr.get("ldap/hostdn"),)
    )
    grp_dn_list = options.lo.searchDn(filter=filter_s)
    log.info("Host is member of following groups: %r", grp_dn_list)
    is_edu_school_member = False
    is_admin_school_member = False
    for grp_dn in grp_dn_list:
        # is grp_dn in list of global school groups?
        if grp_dn in (
            "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,{}".format(ucr.get("ldap/base")),
            "cn=Member-Edukativnetz,cn=ucsschool,cn=groups,{}".format(ucr.get("ldap/base")),
        ):
            log.debug("host is in group %s", grp_dn)
            is_edu_school_member = True
        if grp_dn in (
            "cn=DC-Verwaltungsnetz,cn=ucsschool,cn=groups,{}".format(ucr.get("ldap/base")),
            "cn=Member-Verwaltungsnetz,cn=ucsschool,cn=groups,{}".format(ucr.get("ldap/base")),
        ):
            log.debug("host is in group %s", grp_dn)
            is_admin_school_member = True
        # is dn in list of OU specific school groups?
        if not grp_dn.startswith("cn=OU"):
            continue
        for suffix in (
            "-DC-Edukativnetz,cn=ucsschool,cn=groups,{}".format(ucr.get("ldap/base")),
            "-Member-Edukativnetz,cn=ucsschool,cn=groups,{}".format(ucr.get("ldap/base")),
        ):
            if grp_dn.endswith(suffix):
                log.debug("host is in group %s", grp_dn)
                is_edu_school_member = True
        for suffix in (
            "-DC-Verwaltungsnetz,cn=ucsschool,cn=groups,{}".format(ucr.get("ldap/base")),
            "-Member-Verwaltungsnetz,cn=ucsschool,cn=groups,{}".format(ucr.get("ldap/base")),
        ):
            if grp_dn.endswith(suffix):
                log.debug("host is in group %s", grp_dn)
                is_admin_school_member = True
    return SchoolMembership(is_edu_school_member, is_admin_school_member)


def determine_role_packages(options, package_manager):  # type: (Any, PackageManager) -> List[str]
    if options.server_role in ("domaincontroller_master",):
        return []

    elif options.server_role in ("domaincontroller_backup",):
        # if metapackage is already installed, then stick with it and don't change it
        for pkg_name in (
            "ucs-school-master",
            "ucs-school-singlemaster",
        ):
            if package_manager.is_installed(pkg_name):
                log.info("Found installed metapackage %r. Reusing it.", pkg_name)
                return [pkg_name]
        # if no metapackage has been found, determine package type via master's UCR variable
        result = call_cmd(options, "/usr/sbin/ucr get ucsschool/singlemaster", on_master=True)
        if ucr.is_true(value=result.stdout.strip()):
            log.info("Master is a UCS@school single server system")
            return ["ucs-school-singlemaster"]
        else:
            log.info("Master is part of a multi server environment")
            return ["ucs-school-master"]

    elif options.server_role in ("domaincontroller_slave",):
        # if metapackage is already installed, then stick with it and don't change it
        for pkg_name in ("ucs-school-slave", "ucs-school-nonedu-slave", "ucs-school-central-slave"):
            if package_manager.is_installed(pkg_name):
                log.info("Found installed metapackage %r. Reusing it.", pkg_name)
                return [pkg_name]

        # if no metapackage has been found, then determine slave type via group memberships
        membership = get_school_membership(options)
        if membership.is_edu_school_member:
            return ["ucs-school-slave"]
        elif membership.is_admin_school_member:
            return ["ucs-school-nonedu-slave"]
        else:
            return ["ucs-school-central-slave"]

    elif options.server_role in ("memberserver",):
        return []

    log.warning("System role %r not found!", options.server_role)
    return []


def call_cmd(
    options, cmd, on_master=False
):  # type: (Any, Union[str, List[str]], Optional[bool]) -> StdoutStderr
    if on_master:
        assert isinstance(cmd, str)
        cmd = [
            "univention-ssh",
            "/etc/machine.secret",
            "{}$@{}".format(ucr.get("hostname"), options.master_fqdn),
            cmd,
        ]
    else:
        assert isinstance(cmd, (list, tuple))
    log.info("Calling %r ...", cmd)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode:
        log.error(
            "%s returned with exitcode %s:\n%s\n%s", " ".join(cmd), proc.returncode, stderr, stdout
        )
        sys.exit(1)
    return StdoutStderr(stdout, stderr)


def activate_repository():  # type: () -> None
    """
    Bug #49475: on UCS 4.4-0 DVDs the UCR variable repository/online is false and therefore
    an installation via univention-app will fail. This is a workaround until the installation
    media has been fixed/adapted.
    """
    log.info("repository/online: %r", ucr.get("repository/online"))
    if ucr.is_false("repository/online", False):
        log.warning("The online repository is deactivated. Reactivating it.")
        handler_set(["repository/online=true"])
        cmd = ["/usr/bin/apt-get", "update"]
        log.info("Calling %r ...", cmd)
        returncode = subprocess.call(cmd)
        if returncode:
            log.error("%s failed with exit code %s!", " ".join(cmd), returncode)


def pre_joinscripts_hook(options):  # type: (Any) -> None
    # do not do anything, if we are running within a docker container
    if ucr.get("docker/container/uuid"):
        log.info("This is a docker container... stopping here")
        return

    package_manager = PackageManager(lock=False, always_noninteractive=True)

    pkg_list = determine_role_packages(options, package_manager)
    log.info("Determined role packages: %r", pkg_list)

    # check if UCS@school app is installed/configured/included,
    # if not, then install the same version used by domaincontroller_master
    result = call_cmd(options, ["univention-app", "info", "--as-json"], on_master=False)
    local_status = json.loads(result.stdout)
    ucsschool_installed = any(x.startswith("ucsschool=") for x in local_status.get("installed", []))
    log.info("Installed packages: %r", local_status.get("installed"))
    log.info("Is ucsschool already installed? %r", ucsschool_installed)
    # only install UCS@school if at least one package has to be installed
    if not ucsschool_installed and pkg_list:
        result = call_cmd(options, "/usr/sbin/ucr get version/version", on_master=True)
        master_version = result.stdout.strip()
        result = call_cmd(options, ["ucr", "get", "version/version"], on_master=False)
        local_version = result.stdout.strip()
        app_string = "ucsschool"
        log.info("Master version: %r", master_version)
        log.info("Local version: %r", local_version)
        if master_version == local_version:
            result = call_cmd(options, "/usr/bin/univention-app info --as-json", on_master=True)
            master_app_info = json.loads(result.stdout)
            # master_app_info:  {"compat": "4.3-1 errata0", "upgradable": [], "ucs": "4.3-1 errata0",
            # "installed": ["ucsschool=4.3 v5"]}

            for app_entry in master_app_info.get("installed", []):
                app_name, app_version = app_entry.split("=", 1)
                if app_name == "ucsschool":
                    log.info("Found UCS@school version %r on DC master.", app_version)
                    break
            else:
                log.error(
                    "UCS@school does not seem to be installed on %s! Cannot get app version of "
                    "UCS@school on DC master!",
                    options.master_fqdn,
                )
                sys.exit(1)

            if LooseVersion(app_version) >= LooseVersion("4.4 v7"):
                # Bug #52214: The errata level on the UCS installation DVD (incl. for UCS 4.4-6) may be
                # below the one required by UCS@school 4.4 v7: "4.4-6 errata762". In such a case install
                # a UCS@school app version without that requirement (4.4 v6).
                errata_package = package_manager.get_package("univention-errata-level")
                if not LooseVersion(errata_package.installed.version) >= LooseVersion("4.4.6-762"):
                    app_version = "4.4 v6"
                    log.warning(
                        "Current errata level to low (%r), installing UCS@school version %r instead.",
                        errata_package.installed.version,
                        app_version,
                    )

            app_string = "%s=%s" % (app_string, app_version)

        activate_repository()

        log.info("Updating app center information...")
        cmd = [
            "univention-app",
            "update",
        ]
        returncode = subprocess.call(cmd)
        if returncode:
            log.error("%s failed with exit code %s!", " ".join(cmd), returncode)
            sys.exit(1)

        log.info("Installing %s ...", app_string)
        cmd = [
            "univention-app",
            "install",
            app_string,
            "--skip-check",
            "must_have_valid_license",
            "--do-not-call-join-scripts",
        ]
        returncode = subprocess.call(cmd)
        if returncode:
            log.error("%s failed with exit code %s!", " ".join(cmd), returncode)
            sys.exit(1)

    # if not all packages are installed, then try to install them again
    if not all(package_manager.is_installed(pkg_name) for pkg_name in pkg_list):
        log.info("Not all required packages installed - calling univention-install...")
        subprocess.call(["univention-install", "--force-yes", "--yes"] + pkg_list)


def main():  # type: () -> None
    global log, ucr

    parser = optparse.OptionParser()
    parser.add_option(
        "--server-role",
        dest="server_role",
        default=None,
        action="store",
        help="server role of this system",
    )
    parser.add_option(
        "--master",
        dest="master_fqdn",
        action="store",
        default=None,
        help="FQDN of the UCS master domaincontroller",
    )
    parser.add_option("--binddn", dest="binddn", action="store", default=None, help="LDAP binddn")
    parser.add_option(
        "--bindpwdfile", dest="bindpwdfile", action="store", default=None, help="path to password file"
    )
    parser.add_option(
        "--hooktype",
        dest="hook_type",
        action="store",
        default=None,
        help='join hook type (currently only "join/pre-joinscripts" supported)',
    )
    parser.add_option("-v", "--verbose", action="count", default=3, help="Increase verbosity")
    (options, args) = parser.parse_args()

    if not options.server_role:
        parser.error("Please specify a server role")
    if not options.master_fqdn:
        parser.error("Please specify a FQDN for the master domaincontroller")
    if not options.binddn:
        parser.error("Please specify a LDAP binddn")
    if not options.bindpwdfile:
        parser.error("Please specify a path to a file with a LDAP password")
    if not os.path.isfile(options.bindpwdfile):
        parser.error("The given path for --bindpwdfile is not valid")
    if not options.hook_type:
        parser.error("Please specify a hook type")
    if options.hook_type in ("join/post-joinscripts",):
        parser.error("The specified hook type is not supported by this script")

    options.bindpw = open(options.bindpwdfile, "r").read()

    LEVELS = [logging.FATAL, logging.ERROR, logging.WARN, logging.INFO, logging.DEBUG]
    try:
        level = LEVELS[options.verbose]
    except IndexError:
        level = LEVELS[-1]
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s ucsschool-join-hook: [%(levelname)s] %(message)s",
    )

    log = logging.getLogger(__name__)
    log.info("ucsschool-join-hook.py has been started")
    ucr = ConfigRegistry()
    ucr.load()

    if ucr.is_false("ucsschool/join/hook/join/pre-joinscripts", False):
        log.warning(
            "UCS@school join hook has been disabled via UCR variable "
            "ucsschool/join/hook/join/pre-joinscripts."
        )
        sys.exit(0)

    options.lo = get_lo(options)

    pre_joinscripts_hook(options)

    log.info("ucsschool-join-hook.py is done")


if __name__ == "__main__":
    main()
