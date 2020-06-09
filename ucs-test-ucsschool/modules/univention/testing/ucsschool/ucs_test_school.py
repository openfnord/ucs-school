# -*- coding: utf-8 -*-
#
# UCS test
"""
API for testing UCS@school and cleaning up after performed tests
"""
# Copyright 2014-2020 Univention GmbH
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

# This module (univention.testing.ucsschool) tries to import ucsschool.lib.models.
# Without absolute_import python is looking for lib.modules within THIS file which
# is obviously wrong in this case.
from __future__ import absolute_import

import json
import logging
import os
import random
import subprocess
import sys
import tempfile
from collections import defaultdict

import lazy_object_proxy
import ldap
from ldap import LDAPError

import univention.admin.uldap as udm_uldap
import univention.testing.strings as uts
import univention.testing.ucr
import univention.testing.udm as udm_test
import univention.testing.utils as utils
from ucsschool.lib.models import (
    School,
    SchoolClass,
    Staff,
    Student,
    Teacher,
    TeachersAndStaff,
    User,
    WorkGroup,
)
from ucsschool.lib.models.computer import SchoolComputer
from ucsschool.lib.models.group import ComputerRoom
from ucsschool.lib.models.utils import (
    UniStreamHandler,
    add_stream_logger_to_schoollib,
    get_stream_handler,
)
from ucsschool.lib.roles import (
    create_ucsschool_role_string,
    role_computer_room,
    role_school_admin,
    role_school_class,
    role_staff,
    role_student,
    role_teacher,
    role_workgroup,
)
from univention.admin.uexceptions import noObject

try:
    from typing import Dict, List, Optional, Set, Tuple
except ImportError:
    pass


TEST_OU_CACHE_FILE = "/var/lib/ucs-test/ucsschool-test-ous.json"


def force_ucsschool_logger_colorized_if_has_tty():
    """
    Force the logger "ucsschool" returned by
    :py:func:`ucsschool.models.utils.get_stream_handler()` (and used in
    :py:func:`add_stream_logger_to_schoollib()`) to colorize terminal output in
    case our process has a TTY or our parents process if it's called "ucs-test"
    and has a TTY.

    If ucs-test is run by Jenkins, it won't have the TTY itself, in which case
    the output won't be colorized.
    """
    colorize = False
    if sys.stdout.isatty():
        colorize = True
    else:
        # try to use the stdout of the parent process if it's ucs-test
        ppid = os.getppid()
        with open("/proc/{}/cmdline".format(ppid), "r") as fp:
            if "ucs-test" in fp.read():
                fd = open("/proc/{}/fd/1".format(ppid), "a")
                if fd.isatty():
                    colorize = True
    if colorize:
        # Tell ucssschool.models.utils.UCSTTYColoredFormatter to force colorization.
        # This is required for import processes spawned by us to also ignore the missing TTY.
        os.environ["UCSSCHOOL_FORCE_COLOR_TERM"] = "1"


def get_ucsschool_logger():  # type: () -> logging.Logger
    force_ucsschool_logger_colorized_if_has_tty()
    logger = logging.getLogger("ucsschool")
    logger.setLevel(logging.DEBUG)
    if not any(isinstance(handler, UniStreamHandler) for handler in logger.handlers):
        logger.addHandler(get_stream_handler("DEBUG"))
    return logger


logger = lazy_object_proxy.Proxy(get_ucsschool_logger)  # type: logging.Logger


class SchoolError(Exception):
    pass


class SchoolMissingOU(SchoolError):
    pass


class SchoolLDAPError(SchoolError):
    pass


class Bunch(object):
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


class UCSTestSchool(object):
    ucr = lazy_object_proxy.Proxy(lambda: univention.testing.ucr.UCSTestConfigRegistry().__enter__())
    _test_ous = dict()  # type: Dict[str, List[Tuple[str]]]

    LDAP_BASE = lazy_object_proxy.Proxy(lambda: UCSTestSchool.ucr["ldap/base"])

    PATH_CMD_BASE = "/usr/share/ucs-school-import/scripts"
    PATH_CMD_CREATE_OU = os.path.join(PATH_CMD_BASE, "create_ou")
    PATH_CMD_IMPORT_USER = os.path.join(PATH_CMD_BASE, "import_user")

    CN_STUDENT = lazy_object_proxy.Proxy(
        lambda: UCSTestSchool.ucr.get("ucsschool/ldap/default/container/pupils", "schueler")
    )
    CN_TEACHERS = lazy_object_proxy.Proxy(
        lambda: UCSTestSchool.ucr.get("ucsschool/ldap/default/container/teachers", "lehrer")
    )
    CN_TEACHERS_STAFF = lazy_object_proxy.Proxy(
        lambda: UCSTestSchool.ucr.get(
            "ucsschool/ldap/default/container/teachers-and-staff", "lehrer und mitarbeiter"
        )
    )
    CN_ADMINS = lazy_object_proxy.Proxy(
        lambda: UCSTestSchool.ucr.get("ucsschool/ldap/default/container/admins", "admins")
    )
    CN_STAFF = lazy_object_proxy.Proxy(
        lambda: UCSTestSchool.ucr.get("ucsschool/ldap/default/container/staff", "mitarbeiter")
    )

    def __init__(self):
        add_stream_logger_to_schoollib()
        random.seed()
        self._cleanup_ou_names = set()
        self._ldap_objects_in_test_ous = dict()  # type: Dict[str, Set[str]]
        self.lo = self.open_ldap_connection()
        self.udm = udm_test.UCSTestUDM()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, etraceback):
        if exc_type:
            logger.exception("*** Cleanup after exception: %s %r", exc_type, exc_value)
        try:
            self.cleanup()
        except Exception as exc:
            logger.exception("*** Error during cleanup: %s", exc)
            raise

    @classmethod
    def open_ldap_connection(
        cls, binddn=None, bindpw=None, ldap_server=None, admin=False, machine=False
    ):
        """
        Opens a new LDAP connection using the given user LDAP DN and
        password. The connection is established to the given server or
        (if None is given) to the server defined by the UCR variable
        ldap/server/name is used.
        If admin is set to True, a connection is setup by getAdminConnection().
        If machine is set to True, a connection to the master is setup by getMachoneConnection().
        """
        assert not (admin and machine)
        assert not (
            binddn or bindpw
        ), 'Arguments "binddn" and "bindpw" are ignored and UCSTestDomainAdminCredentials() used.'

        account = utils.UCSTestDomainAdminCredentials()
        if not ldap_server:
            ldap_server = cls.ucr.get("ldap/master")
        port = int(cls.ucr.get("ldap/server/port", 7389))

        try:
            if admin:
                lo = udm_uldap.getAdminConnection()[0]
            elif machine:
                lo = udm_uldap.getMachineConnection(ldap_master=True)[0]
            else:
                lo = udm_uldap.access(
                    host=ldap_server,
                    port=port,
                    base=cls.ucr.get("ldap/base"),
                    binddn=account.binddn,
                    bindpw=account.bindpw,
                    start_tls=2,
                )
        except noObject:
            raise
        except LDAPError as exc:
            raise SchoolLDAPError("Opening LDAP connection failed: %s" % (exc,))

        return lo

    def _remove_udm_object(self, module, dn, raise_exceptions=False):
        """
            Tries to remove UDM object specified by given dn.
            Return None on success or error message.
        """
        try:
            dn = self.lo.searchDn(base=dn)[0]
        except (ldap.NO_SUCH_OBJECT, IndexError, noObject):
            if raise_exceptions:
                raise
            return "missing object"

        msg = None
        cmd = [udm_test.UCSTestUDM.PATH_UDM_CLI_CLIENT_WRAPPED, module, "remove", "--dn", dn]
        logger.info("*** Calling following command: %r", cmd)
        retval = subprocess.call(cmd)
        if retval:
            msg = "*** ERROR: failed to remove UCS@school %s object: %s" % (module, dn)
            logger.error(msg)
        return msg

    def _set_password(self, userdn, password, raise_exceptions=False):
        """
            Tries to set a password for the given user.
            Return None on success or error message.
        """
        try:
            dn = self.lo.searchDn(base=userdn)[0]
        except (ldap.NO_SUCH_OBJECT, IndexError):
            if raise_exceptions:
                raise
            return "missing object"

        msg = None
        cmd = [
            udm_test.UCSTestUDM.PATH_UDM_CLI_CLIENT_WRAPPED,
            "users/user",
            "modify",
            "--dn",
            dn,
            "--set",
            "password=%s" % password,
        ]
        logger.info("*** Calling following command: %r", cmd)
        retval = subprocess.call(cmd)
        if retval:
            msg = "ERROR: failed to set password for UCS@school user %s" % (userdn)
            logger.info(msg)
        return msg

    def cleanup(self, wait_for_replication=True):
        """ Cleanup all objects created by the UCS@school test environment """
        logger.info("Performing UCSTestSchool cleanup...")
        for ou_name in self._cleanup_ou_names:
            self.cleanup_ou(ou_name, wait_for_replication=False)

        if self._ldap_objects_in_test_ous:
            # create_ou() was used with use_cache=True
            for k, v in self._ldap_objects_in_test_ous.items():
                try:
                    res = self.diff_ldap_status(self.lo, v, k)
                except noObject:
                    continue
                for dn in res.new:
                    filter_s, base = dn.split(",", 1)
                    objs = self.lo.search(filter_s, base=base, attr=["univentionObjectType"])
                    if objs:
                        univention_object_type = objs[0][1].get("univentionObjectType")
                        if univention_object_type:
                            self.udm._cleanup.setdefault(univention_object_type[0], []).append(dn)
                        else:
                            logger.info(
                                '*** Removing LDAP object without "univentionObjectType" directly (not using UDM): %r',
                                dn,
                            )
                            try:
                                self.lo.delete(dn)
                            except noObject as exc:
                                logger.error("*** %s", exc)

        logger.info("Performing UDM cleanup...")
        self.udm.cleanup()
        logger.info("Performing UCR cleanup...")
        self.ucr.revert_to_original_registry()

        if wait_for_replication:
            utils.wait_for_replication()
        logger.info("UCSTestSchool cleanup done")

    def cleanup_ou(self, ou_name, wait_for_replication=True):
        """ Removes the given school ou and all its corresponding objects like groups """

        logger.info("*** Purging OU %r and related objects", ou_name)
        # remove OU specific groups
        for grpdn in (
            "cn=OU%(ou)s-Member-Verwaltungsnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=OU%(ou)s-Member-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=OU%(ou)s-Klassenarbeit,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=OU%(ou)s-DC-Verwaltungsnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=admins-%(ou)s,cn=ouadmins,cn=groups,%(basedn)s",
        ):
            grpdn = grpdn % {"ou": ou_name, "basedn": self.ucr.get("ldap/base")}
            self._remove_udm_object("groups/group", grpdn)

        # remove OU recursively
        if self.ucr.is_true("ucsschool/ldap/district/enable"):
            district_ou_dn = "ou=%(district)s,%(basedn)s" % {
                "district": ou_name[0:2],
                "basedn": self.ucr.get("ldap/base"),
            }
            oudn = "ou=%(ou)s,%(district_ou_dn)s" % {"ou": ou_name, "district_ou_dn": district_ou_dn}
        else:
            district_ou_dn = ""
            oudn = "ou=%(ou)s,%(basedn)s" % {"ou": ou_name, "basedn": self.ucr.get("ldap/base")}

        # get list of OU and objects below - sorted by length, longest first (==> leafs first)
        ok = True
        logger.info("Removing school %r (%s) and its children ...", ou_name, oudn)
        try:
            obj_list = sorted(
                self.lo.searchDn(base=oudn, scope="sub"), key=lambda x: len(x), reverse=True
            )
        except noObject:
            logger.warn("OU has already been removed.")
            ok = False
        else:
            for obj_dn in obj_list:
                try:
                    self.lo.delete(obj_dn)
                except LDAPError as exc:
                    logger.error("Cannot remove %r: %s", obj_dn, exc)
                    ok = False
                else:
                    logger.info("Removed %s", obj_dn)
        log_func = logger.info if ok else logger.error
        log_func(
            "*** Purging OU %r and its children objects (%s): %s\n\n",
            ou_name,
            oudn,
            "done" if ok else "failed",
        )

        for ou_list in self._test_ous.values():
            try:
                ou_list.remove((ou_name, oudn))
            except ValueError:
                pass

        if district_ou_dn:
            logger.info("*** Deleting district OU %s (%s)...", ou_name[0:2], district_ou_dn)
            self._remove_udm_object("container/ou", district_ou_dn)

            if wait_for_replication:
                utils.wait_for_replication()

    @classmethod
    def check_name_edudc(cls, name_edudc):
        if isinstance(name_edudc, str):
            if name_edudc.lower() == cls.ucr.get("ldap/master", "").split(".", 1)[0].lower():
                logger.info(
                    "*** It is not allowed to set the master as name_edudc ==> resetting name_edudc to None"
                )
                name_edudc = None
            elif any(
                [
                    name_edudc.lower() == backup.split(".", 1)[0].lower()
                    for backup in cls.ucr.get("ldap/backup", "").split(" ")
                ]
            ):
                logger.info(
                    "*** It is not allowed to set any backup as name_edudc ==> resetting name_edudc to None"
                )
                name_edudc = None
        return name_edudc

    def create_ou(
        self,
        ou_name=None,
        name_edudc=None,
        name_admindc=None,
        displayName="",
        name_share_file_server=None,
        use_cli=False,
        wait_for_replication=True,
        use_cache=True,
    ):
        """
        Creates a new OU with random or specified name. The function may also set a specified
        displayName. If "displayName" is None, a random displayName will be set. If "displayName"
        equals to the empty string (''), the displayName won't be set. "name_edudc" may contain
        the optional name for an educational dc slave. "name_admindc" may contain
        the optional name for an administrative dc slave. If name_share_file_server is set, the
        class share file server and the home share file server will be set.
        If use_cli is set to True, the old CLI interface is used. Otherwise the UCS@school python
        library is used.
        If use_cache is True (default) and an OU was created in a previous test with the same arguments,
        it will be reused. -> If ou_name and displayName are None, instead of creating new random names,
        the existing test-OU will be returned.
        PLEASE NOTE: if name_edudc is set to the hostname of the master or backup, name_edudc will be unset automatically,
            because it's not allowed to specify the hostname of the master or any backup in any situation!

        Return value: (ou_name, ou_dn)
            ou_name: name of the created OU
            ou_dn:   DN of the created OU object
        """
        # it is not allowed to set the master as name_edudc ==> resetting name_edudc
        name_edudc = self.check_name_edudc(name_edudc)
        if use_cache and not self._test_ous:
            self.load_test_ous()
        cache_key = (ou_name, name_edudc, name_admindc, displayName, name_share_file_server, use_cli)
        if use_cache and self._test_ous.get(cache_key):
            res = random.choice(self._test_ous[cache_key])
            logger.info(
                "*** Found %d OUs in cache for arguments %r, using %r.",
                len(self._test_ous[cache_key]),
                cache_key,
                res,
            )
            self._ldap_objects_in_test_ous.setdefault(res[1], set()).update(
                self.get_ldap_status(self.lo, res[1])
            )
            return res

        # create random display name for OU
        charset = uts.STR_ALPHANUMDOTDASH + uts.STR_ALPHA.upper() + '()[]/,;:_#"+*@<>~ßöäüÖÄÜ$%&!     '
        if displayName is None:
            displayName = uts.random_string(length=random.randint(5, 50), charset=charset)

        # create random OU name
        if not ou_name:
            ou_name = uts.random_string(length=random.randint(3, 12))

        # remember OU name for cleanup
        if not use_cache:
            self._cleanup_ou_names.add(ou_name)

        if not use_cli:
            kwargs = {"name": ou_name, "dc_name": name_edudc}
            if name_admindc:
                kwargs["dc_name_administrative"] = name_admindc
            if name_share_file_server:
                kwargs["class_share_file_server"] = name_share_file_server
                kwargs["home_share_file_server"] = name_share_file_server
            if displayName:
                kwargs["display_name"] = displayName

            logger.info("*** Creating new OU %r", ou_name)
            School.invalidate_all_caches()
            School.init_udm_module(
                self.lo
            )  # TODO FIXME has to be fixed in ucs-school-lib - should be done automatically
            result = School(**kwargs).create(self.lo)
            logger.info("*** Result of School(...).create(): %r", result)
        else:
            # build command line
            cmd = [self.PATH_CMD_CREATE_OU]
            if displayName:
                cmd += ["--displayName", displayName]
            cmd += [ou_name]
            if name_edudc:
                cmd += [name_edudc]

            logger.info("*** Calling following command: %r", cmd)
            retval = subprocess.call(cmd)
            if retval:
                utils.fail("create_ou failed with exitcode %s" % retval)

        if wait_for_replication:
            utils.wait_for_replication()

        if self.ucr.is_true("ucsschool/ldap/district/enable"):
            logger.warning("******* district mode is enabled!! *******")
        ou_dn = self.get_ou_base_dn(ou_name)
        if use_cache:
            logger.info("*** Storing OU %r in cache with key %r.", ou_name, cache_key)
            self._test_ous.setdefault(cache_key, []).append((ou_name, ou_dn))
            self._ldap_objects_in_test_ous.setdefault(ou_dn, set()).update(
                self.get_ldap_status(self.lo, ou_dn)
            )
            self.store_test_ous()
        return ou_name, ou_dn

    def create_multiple_ous(
        self,
        num,
        name_edudc=None,
        name_admindc=None,
        displayName="",
        name_share_file_server=None,
        use_cli=False,
        wait_for_replication=True,
        use_cache=True,
    ):
        """
        Create `num` OUs with each the same arguments and a random ou_name,
        without either effectively dodging the OU-cache or each time getting
        the same OU (with use_cache=True). All arguments except `num` plus a
        random name for the ou (argument "ou_name") will be passed to
        create_ou().

        :param num: int - number or OUs to create
        :return: list - list of tuples returned by create_ou()
        """
        if not use_cache:
            return [
                self.create_ou(
                    None,
                    name_edudc,
                    name_admindc,
                    displayName,
                    name_share_file_server,
                    use_cli,
                    wait_for_replication,
                    use_cache,
                )
                for _ in range(num)
            ]

        if not self._test_ous:
            self.load_test_ous()
        name_edudc = self.check_name_edudc(name_edudc)
        cache_key = (None, name_edudc, name_admindc, displayName, name_share_file_server, use_cli)
        while len(self._test_ous.setdefault(cache_key, [])) < num:
            ou_name, ou_dn = self.create_ou(
                None,
                name_edudc,
                name_admindc,
                displayName,
                name_share_file_server,
                use_cli,
                wait_for_replication,
                False,
            )
            logger.info("*** Storing OU %r in cache with key %r.", ou_name, cache_key)
            self._test_ous.setdefault(cache_key, []).append((ou_name, ou_dn))
            self.store_test_ous()
            self._cleanup_ou_names.remove(ou_name)
        random.shuffle(self._test_ous[cache_key])
        res = self._test_ous[cache_key][:num]
        for ou_name, ou_dn in res:
            self._ldap_objects_in_test_ous.setdefault(ou_dn, set()).update(
                self.get_ldap_status(self.lo, ou_dn)
            )
        logger.info(
            "*** Chose %d/%d OUs from cache for arguments %r: %r.",
            len(res),
            len(self._test_ous[cache_key]),
            cache_key,
            res,
        )
        return res

    def get_district(self, ou_name):
        try:
            return ou_name[:2]
        except IndexError:
            raise SchoolError('The OU name "%s" is too short for district mode' % ou_name)

    def get_ou_base_dn(self, ou_name):
        """
        Returns the LDAP DN for the given school OU name (the district mode will be considered).
        """
        return "%(school)s,%(district)s%(basedn)s" % {
            "school": "ou=%s" % ou_name,
            "basedn": self.LDAP_BASE,
            "district": "ou=%s," % self.get_district(ou_name)
            if self.ucr.is_true("ucsschool/ldap/district/enable")
            else "",
        }

    def get_user_container(self, ou_name, is_teacher=False, is_staff=False):
        """
        Returns user container for specified user role and ou_name.
        """
        if is_teacher and is_staff:
            return "cn=%s,cn=users,%s" % (self.CN_TEACHERS_STAFF, self.get_ou_base_dn(ou_name))
        if is_teacher:
            return "cn=%s,cn=users,%s" % (self.CN_TEACHERS, self.get_ou_base_dn(ou_name))
        if is_staff:
            return "cn=%s,cn=users,%s" % (self.CN_STAFF, self.get_ou_base_dn(ou_name))
        return "cn=%s,cn=users,%s" % (self.CN_STUDENT, self.get_ou_base_dn(ou_name))

    def get_workinggroup_dn(self, ou_name, group_name):
        """
        Return the DN of the specified working group.
        """
        return "cn=%s-%s,cn=schueler,cn=groups,%s" % (ou_name, group_name, self.get_ou_base_dn(ou_name))

    def get_workinggroup_share_dn(self, ou_name, group_name):
        """
        Return the DN of the share object for the specified working group.
        """
        return "cn=%s-%s,cn=shares,%s" % (ou_name, group_name, self.get_ou_base_dn(ou_name))

    def create_teacher(self, *args, **kwargs):
        """
        Accepts same arguments as :py:func:`create_user()`, and sets `is_staff`
        and `is_teacher`accordingly.
        """
        return self.create_user(*args, is_teacher=True, is_staff=False, **kwargs)

    def create_student(self, *args, **kwargs):
        """
        Accepts same arguments as :py:func:`create_user()`, and sets `is_staff`
        and `is_teacher`accordingly.
        """
        return self.create_user(*args, is_teacher=False, is_staff=False, **kwargs)

    def create_exam_student(self, *args, **kwargs):
        """NOT FUNCTIONAL!"""
        raise NotImplementedError

    def create_staff(self, *args, **kwargs):
        """
        Accepts same arguments as :py:func:`create_user()`, and sets `is_staff`
        and `is_teacher`accordingly.
        """
        return self.create_user(*args, is_staff=True, is_teacher=False, **kwargs)

    def create_teacher_and_staff(self, *args, **kwargs):
        """
        Accepts same arguments as :py:func:`create_user()`, and sets `is_staff`
        and `is_teacher`accordingly.
        """
        return self.create_user(*args, is_staff=True, is_teacher=True, **kwargs)

    def create_user(
        self,
        ou_name,  # type: str
        schools=None,  # type: Optional[List[str]]
        username=None,  # type: Optional[str]
        firstname=None,  # type: Optional[str]
        lastname=None,  # type: Optional[str]
        classes=None,  # type: Optional[str]
        mailaddress=None,  # type: Optional[str]
        is_teacher=False,  # type: Optional[bool]
        is_staff=False,  # type: Optional[bool]
        is_active=True,  # type: Optional[bool]
        password="univention",  # type: Optional[str]
        use_cli=False,  # type: Optional[bool]
        wait_for_replication=True,  # type: Optional[bool]
    ):  # type: (...) -> Tuple[str, str]
        """
        Create a user in specified OU with given attributes. If attributes are not specified, random
        values will be used for username, firstname and lastname. If password is not None, the given
        password will be set for this user.

        Return value: (user_name, user_dn)
            user_name: name of the created user
            user_dn:   DN of the created user object
        """
        if not ou_name:
            raise SchoolMissingOU("No OU name specified")

        # set default values
        if username is None:
            username = uts.random_username()
        if firstname is None:
            firstname = uts.random_string(length=10, numeric=False)
        if lastname is None:
            lastname = uts.random_string(length=10, numeric=False)
        if mailaddress is None:
            mailaddress = ""
        if schools is None:
            schools = [ou_name]

        user_dn = "uid=%s,%s" % (username, self.get_user_container(ou_name, is_teacher, is_staff))
        if use_cli:
            if classes is None:
                classes = ""
            if classes:
                if not all(["-" in c for c in classes.split(",")]):
                    utils.fail("*** Class names must be <school-ou>-<class-name>.")
            # create import file
            line = "A\t%s\t%s\t%s\t%s\t%s\t\t%s\t%d\t%d\t%d\n" % (
                username,
                lastname,
                firstname,
                ou_name,
                classes,
                mailaddress,
                int(is_teacher),
                int(is_active),
                int(is_staff),
            )
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_file.write(line)
                tmp_file.flush()

                cmd = [self.PATH_CMD_IMPORT_USER, tmp_file.name]
                logger.info("*** Calling following command: %r", cmd)
                retval = subprocess.call(cmd)
                if retval:
                    utils.fail("import_user failed with exitcode %s" % retval)

            if is_staff and is_teacher:
                roles = [role_staff, role_teacher]
            elif is_staff and not is_teacher:
                roles = [role_staff]
            elif not is_staff and is_teacher:
                roles = [role_teacher]
            else:
                roles = [role_student]

            if password is not None:
                self._set_password(user_dn, password)
        else:
            school_classes = defaultdict(list)
            if classes:
                for kls in classes.split(","):
                    school_classes[kls.partition("-")[0]].append(kls)
            kwargs = {
                "school": ou_name,
                "schools": schools,
                "name": username,
                "firstname": firstname,
                "lastname": lastname,
                "email": mailaddress,
                "password": password,
                "disabled": not is_active,
                "school_classes": dict(school_classes),
            }
            cls = Student
            if is_teacher and is_staff:
                cls = TeachersAndStaff
            elif is_teacher and not is_staff:
                cls = Teacher
            elif not is_teacher and is_staff:
                cls = Staff
            logger.info("*** Creating new %s %r with %r.", cls.__name__, username, kwargs)
            User.invalidate_all_caches()
            User.init_udm_module(
                self.lo
            )  # TODO FIXME has to be fixed in ucs-school-lib - should be done automatically
            roles = cls.default_roles
            result = cls(**kwargs).create(self.lo)
            logger.info("*** Result of %s(...).create(): %r", cls.__name__, result)

        if wait_for_replication:
            utils.wait_for_replication()

        utils.verify_ldap_object(
            user_dn,
            expected_attr={
                "ucsschoolRole": [create_ucsschool_role_string(role, ou_name) for role in roles]
            },
            strict=False,
            should_exist=True,
        )
        return username, user_dn

    def create_school_admin(
        self,
        ou_name,  # type: str
        schools=None,  # type: Optional[List[str]]
        is_staff=None,  # type: Optional[bool]
        is_teacher=None,  # type: Optional[bool]
        wait_for_replication=True,  # type: Optional[bool]
        *args,
        **kwargs
    ):  # type: (...) -> Tuple[str, str]
        """Accepts same arguments as :py:func:`create_user()`."""
        schools = schools if schools else [ou_name]
        assert ou_name in schools
        groups = [
            "cn=admins-%s,cn=ouadmins,cn=groups,%s" % (school, self.LDAP_BASE) for school in schools
        ]
        if is_staff is None:
            is_staff = random.choice((True, False))
        if is_teacher is None:
            is_teacher = random.choice((True, False))
        tmp_role = not is_staff and not is_teacher
        logger.info(
            "*** Creating new SchoolAdmin from school user (is_staff=%r, is_teacher=%r)...",
            is_staff,
            is_teacher,
        )
        school_admin, dn = self.create_user(
            ou_name=ou_name,
            schools=schools,
            is_staff=is_staff or tmp_role,
            is_teacher=is_teacher,  # add a role, or create_user() will create a student, remove role later
            wait_for_replication=wait_for_replication,
            *args,
            **kwargs
        )
        user = User.from_dn(dn, ou_name, self.lo)
        user_udm = user.get_udm_object(self.lo)
        user_udm["groups"].extend(groups)
        user_udm.options.append("ucsschoolAdministrator")
        if tmp_role:
            # remove temporary role
            user_udm.options.remove("ucsschoolStaff")
            for s in schools:
                user_udm["ucsschoolRole"].remove(create_ucsschool_role_string(role_staff, s))
        # TODO: investigate: the school_admin role should automatically be added
        user_udm["ucsschoolRole"].extend(
            create_ucsschool_role_string(role_school_admin, s) for s in schools
        )
        user_udm.modify()
        logger.info("*** SchoolAdmin created from %s ***", user.__class__.__name__)
        if wait_for_replication:
            utils.wait_for_replication()
        expected_ocs = {"ucsschoolAdministrator"}
        roles = []
        if is_staff:
            expected_ocs.add("ucsschoolStaff")
            roles.extend(create_ucsschool_role_string(role_staff, s) for s in schools)
        if is_teacher:
            expected_ocs.add("ucsschoolTeacher")
            roles.extend(create_ucsschool_role_string(role_teacher, s) for s in schools)
        roles.extend(create_ucsschool_role_string(role_school_admin, s) for s in schools)
        utils.verify_ldap_object(
            dn,
            expected_attr={
                "ucsschoolSchool": schools,
                "ucsschoolRole": roles,
                "objectClass": expected_ocs,
            },
            strict=False,
            should_exist=True,
        )
        return school_admin, dn

    def create_domain_admin(
        self,
        ou_name,  # type: str
        username=None,  # type: Optional[str]
        password="univention",  # type: Optional[str]
    ):  # type: (...) -> Tuple[str, str]
        position = "cn=admins,cn=users,%s" % (self.get_ou_base_dn(ou_name))
        groups = ["cn=Domain Admins,cn=groups,%s" % (self.LDAP_BASE,)]
        if username is None:
            username = uts.random_username()
        kwargs = {
            "username": username,
            "password": password,
        }
        dn, domain_admin = self.udm.create_user(position=position, groups=groups, **kwargs)
        return domain_admin, dn

    def create_global_user(
        self,
        username=None,  # type: Optional[str]
        password="univention",  # type: Optional[str]
    ):  # type: (...) -> Tuple[str, str]
        position = "cn=users,%s" % (self.LDAP_BASE,)
        if username is None:
            username = uts.random_username()
        kwargs = {
            "username": username,
            "password": password,
        }
        dn, global_user = self.udm.create_user(position=position, **kwargs)
        return global_user, dn

    def create_school_class(
        self,
        ou_name,  # type: str
        class_name=None,  # type: Optional[str]
        description=None,  # type: Optional[str]
        users=None,  # type: Optional[List[str]]
        wait_for_replication=True,  # type: Optional[bool]
    ):  # type: (...) -> Tuple[str, str]
        if class_name is None:
            class_name = uts.random_username()
        if not class_name.startswith("{}-".format(ou_name)):
            class_name = "{}-{}".format(ou_name, class_name)
        grp_dn = "cn={},cn=klassen,cn=schueler,cn=groups,ou={},{}".format(
            class_name, ou_name, self.LDAP_BASE
        )
        kwargs = {
            "school": ou_name,
            "name": class_name,
            "description": description,
            "users": users or [],
        }
        logger.info("*** Creating new school class %r with %r...", class_name, kwargs)
        SchoolClass.invalidate_all_caches()
        SchoolClass.init_udm_module(self.lo)
        result = SchoolClass(**kwargs).create(self.lo)
        logger.info("*** Result of SchoolClass(...).create(): %r", result)

        if wait_for_replication:
            utils.wait_for_replication()
        utils.verify_ldap_object(
            grp_dn,
            expected_attr={"ucsschoolRole": [create_ucsschool_role_string(role_school_class, ou_name)]},
            strict=False,
            should_exist=True,
        )
        return class_name, grp_dn

    def create_workgroup(
        self, ou_name, workgroup_name=None, description=None, users=None, wait_for_replication=True
    ):
        """
        Creates a new workgroup in specified ou <ou_name>. If no name for the workgroup is specified,
        a random name is used. <name> has to be of format "<OU>-<WGNAME>" or "<WGNAME>".
        Group members may also be specified a list of user DNs in <users>.
        """
        if workgroup_name is None:
            workgroup_name = uts.random_username()
        if not workgroup_name.startswith("{}-".format(ou_name)):
            workgroup_name = "{}-{}".format(ou_name, workgroup_name)
        grp_dn = "cn={},cn=schueler,cn=groups,ou={},{}".format(workgroup_name, ou_name, self.LDAP_BASE)
        kwargs = {
            "school": ou_name,
            "name": workgroup_name,
            "description": description,
            "users": users or [],
        }
        logger.info("*** Creating new WorkGroup %r with %r...", workgroup_name, kwargs)
        WorkGroup.invalidate_all_caches()
        WorkGroup.init_udm_module(self.lo)
        result = WorkGroup(**kwargs).create(self.lo)
        logger.info("*** Result of WorkGroup(...).create(): %r", result)

        if wait_for_replication:
            utils.wait_for_replication()
        utils.verify_ldap_object(
            grp_dn,
            expected_attr={"ucsschoolRole": [create_ucsschool_role_string(role_workgroup, ou_name)]},
            strict=False,
            should_exist=True,
        )
        return workgroup_name, grp_dn

    def create_computerroom(
        self,
        ou_name,
        name=None,
        description=None,
        host_members=None,
        wait_for_replication=True,
        teacher_computers=[],
    ):
        """
        Create a room in specified OU with given attributes. If attributes are not specified, random
        values will be used for roomname and description.

        Return value: (room_name, room_dn)
            room_name: name of the created room
            room_dn:   DN of the created room object
        """
        if not ou_name:
            raise SchoolMissingOU("No OU name specified")

        # set default values
        if name is None:
            name = uts.random_name()
        if description is None:
            description = uts.random_string(length=10, numeric=False)

        host_members = host_members or []
        if not isinstance(host_members, (list, tuple)):
            host_members = [host_members]
        kwargs = {
            "school": ou_name,
            "name": "%s-%s" % (ou_name, name),
            "description": description,
            "hosts": host_members,
        }
        logger.info("*** Creating new room %r", name)
        obj = ComputerRoom(**kwargs)
        result = obj.create(self.lo)
        logger.info("*** Result of ComputerRoom(...).create(): %r", result)
        logger.info("*** Setting up teacher computers: {}".format(teacher_computers))
        for teacher_pc in teacher_computers:
            pc = SchoolComputer.from_dn(teacher_pc, ou_name, self.lo)
            pc.teacher_computer = True
            pc.modify(self.lo)
        logger.info("*** Teacher computer set up")
        if wait_for_replication:
            utils.wait_for_replication()
        utils.verify_ldap_object(
            obj.dn,
            expected_attr={"ucsschoolRole": [create_ucsschool_role_string(role_computer_room, ou_name)]},
            strict=False,
            should_exist=True,
        )
        return name, result

    def create_windows(self):
        pass

    def create_mac(self):
        pass

    def create_ucc(self):
        pass

    def create_ip_managed_client(self):
        pass

    def create_school_dc_slave(self):
        pass

    def delete_test_ous(self):
        if not self._test_ous:
            self.load_test_ous()
        logger.info("self._test_ous=%r", self._test_ous)
        all_test_ous = []
        for test_ous in self._test_ous.values():
            all_test_ous.extend([ou_name for ou_name, on_dn in test_ous])
        for ou_name in all_test_ous:
            self.cleanup_ou(ou_name)
        self.store_test_ous()

    @classmethod
    def load_test_ous(cls):
        cls._test_ous = dict()
        try:
            with open(TEST_OU_CACHE_FILE, "rb") as fp:
                loaded = json.load(fp)
        except IOError as exc:
            logger.info("*** Warning: reading %r: %s", TEST_OU_CACHE_FILE, exc)
            return
        keys = loaded.pop("keys")
        values = loaded.pop("values")
        for k, v in values.items():
            # convert lists to tuples
            # convert unicode to str
            cls._test_ous[tuple(keys[k])] = [tuple(map(str, x)) for x in v]

    @classmethod
    def store_test_ous(cls):
        with open(TEST_OU_CACHE_FILE, "wb") as fp:
            # json needs strings as keys, must split data
            res = {"keys": dict(), "values": dict()}
            for num, (k, v) in enumerate(cls._test_ous.items()):
                res["keys"][num] = k
                res["values"][num] = v
            try:
                json.dump(res, fp)
            except IOError as exc:
                logger.info("*** Error writing to %r: %s", TEST_OU_CACHE_FILE, exc)

    @staticmethod
    def get_ldap_status(lo, base=""):
        return set(lo.searchDn(base=base))

    @staticmethod
    def diff_ldap_status(lo, old_ldap_status, base=""):
        new_ldap_status = set(lo.searchDn(base=base))
        new_objects = new_ldap_status - old_ldap_status
        removed_objects = old_ldap_status - new_ldap_status
        return Bunch(new=new_objects, removed=removed_objects)


class NameDnObj(object):
    def __init__(self, name=None, dn=None):  # type: (str, str) -> None
        self.name = name
        self.dn = dn


class AutoMultiSchoolEnv_Generic(object):
    def __init__(self):  # type: () -> None
        self.master = None  # type: Optional[NameDnObj]
        self.backup = None  # type: Optional[NameDnObj]
        self.slave = None  # type: Optional[NameDnObj]
        self.member = None  # type: Optional[NameDnObj]
        self.winclient = None  # type: Optional[NameDnObj]
        self.domain_admin = None  # type: Optional[NameDnObj]
        self.domain_user = None  # type: Optional[NameDnObj]


class AutoMultiSchoolEnv_School(object):
    def __init__(self):  # type: () -> None
        self.dn = None  # type: Optional[str]
        self.name = None  # type: Optional[str]
        self.teacher = None  # type: Optional[NameDnObj]
        self.teacher_staff = None  # type: Optional[NameDnObj]
        self.staff = None  # type: Optional[NameDnObj]
        self.student = None  # type: Optional[NameDnObj]
        self.admin1 = None  # type: Optional[NameDnObj]
        self.admin2 = None  # type: Optional[NameDnObj]
        self.schoolserver = None  # type: Optional[NameDnObj]
        self.winclient = None  # type: Optional[NameDnObj]
        self.class2 = None  # type: Optional[NameDnObj]
        self.workgroup1 = None  # type: Optional[NameDnObj]
        self.room1 = None  # type: Optional[NameDnObj]


class AutoMultiSchoolEnv(UCSTestSchool):
    def __init__(self):  # type: () -> None
        super(AutoMultiSchoolEnv, self).__init__()

        self.generic = AutoMultiSchoolEnv_Generic()
        self.schoolA = AutoMultiSchoolEnv_School()
        self.schoolB = AutoMultiSchoolEnv_School()
        self.schoolC = AutoMultiSchoolEnv_School()

    def __enter__(self):
        logger.info("---[START /etc/ldap/slapd.conf]---")
        logger.info(open("/etc/ldap/slapd.conf", "r").read())
        logger.info("---[END /etc/ldap/slapd.conf]---")
        for handler in logger.handlers:
            handler.flush()
        return super(AutoMultiSchoolEnv, self).__enter__()

    def create_multi_env_global_objects(self):
        self.generic.master = NameDnObj(
            self.ucr["hostname"],
            self.lo.searchDn(filter="univentionObjectType=computers/domaincontroller_master")[0],
        )
        self.generic.backup = NameDnObj(
            "schoolTestBackup",
            self.udm.create_object(
                "computers/domaincontroller_backup",
                name="schoolTestBackup",
                position="cn=dc,cn=computers,%(ldap/base)s" % self.ucr,
                domain=self.ucr.get("domainname"),
                mac=uts.random_mac(),
                ip=uts.random_ip(),
                password="univention",
            ),
        )
        self.generic.slave = NameDnObj(
            "schoolTestSlave",
            self.udm.create_object(
                "computers/domaincontroller_slave",
                name="schoolTestSlave",
                position="cn=dc,cn=computers,%(ldap/base)s" % self.ucr,
                domain=self.ucr.get("domainname"),
                mac=uts.random_mac(),
                ip=uts.random_ip(),
                password="univention",
            ),
        )
        self.generic.member = NameDnObj(
            "schoolTestMember",
            self.udm.create_object(
                "computers/memberserver",
                name="schoolTestMember",
                position="cn=computers,%(ldap/base)s" % self.ucr,
                domain=self.ucr.get("domainname"),
                mac=uts.random_mac(),
                ip=uts.random_ip(),
                password="univention",
            ),
        )
        self.generic.winclient = NameDnObj(
            "schoolTestWinDom",
            self.udm.create_object(
                "computers/windows",
                name="schoolTestWinDom",
                position="cn=computers,%(ldap/base)s" % self.ucr,
                mac=uts.random_mac(),
                ip=uts.random_ip(),
            ),
        )
        self.generic.domain_user = NameDnObj(
            "domainUser", self.udm.create_user(username="domainUser")[0]
        )
        self.generic.domain_admin = NameDnObj(
            "Administrator", "uid=Administrator,cn=users,%(ldap/base)s" % self.ucr
        )

    def create_multi_env_school_objects(self):
        for suffix, school in (
            ("A", self.schoolA),
            ("B", self.schoolB),
            ("C", self.schoolC),
        ):
            logger.info("---%s-----------------------------------------------------", suffix)
            school.name, school.dn = self.create_ou(
                ou_name="school%s" % (suffix,), name_edudc="schooldc%s" % (suffix,)
            )

            schools = {
                "A": [self.schoolA.name],
                "B": [self.schoolA.name, self.schoolB.name],
                "C": [self.schoolC.name],
            }[suffix]

            school.teacher = NameDnObj(
                *self.create_user(
                    school.name,
                    username="teacher%s" % (suffix,),
                    schools=schools,
                    is_teacher=True,
                    classes="%s-class1" % (school.name,),
                )
            )
            school.teacher_staff = NameDnObj(
                *self.create_user(
                    school.name,
                    username="teachstaff%s" % (suffix,),
                    schools=schools,
                    is_teacher=True,
                    is_staff=True,
                    classes="%s-class1" % (school.name,),
                )
            )
            school.staff = NameDnObj(
                *self.create_user(
                    school.name, username="staff%s" % (suffix,), schools=schools, is_staff=True
                )
            )
            school.student = NameDnObj(
                *self.create_user(
                    school.name,
                    username="student%s" % (suffix,),
                    schools=schools,
                    classes="%s-class1" % (school.name,),
                )
            )
            school.admin1 = NameDnObj(
                *self.create_school_admin(
                    school.name, username="schooladmin1%s" % (suffix,), schools=schools
                )
            )
            school.admin2 = NameDnObj(
                *self.create_school_admin(
                    school.name, username="schooladmin2%s" % (suffix,), schools=schools
                )
            )

            school.schoolserver = NameDnObj(
                "",
                self.lo.searchDn(
                    base=school.dn, filter="univentionObjectType=computers/domaincontroller_slave"
                )[0],
            )
            # self.udm does not allow modification of existing objects
            cmd = [
                "/usr/sbin/udm-test",
                "computers/domaincontroller_slave",
                "modify",
                "--dn",
                school.schoolserver.dn,
                "--set",
                "password=univention",
            ]
            child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            (stdout, stderr) = child.communicate()

            school.winclient = NameDnObj(
                "schoolwin%s" % (suffix,),
                self.udm.create_object(
                    "computers/windows",
                    name="schoolwin%s" % (suffix,),
                    position="cn=computers,%s" % (school.dn,),
                    mac=uts.random_mac(),
                    ip=uts.random_ip(),
                ),
            )

            # create additional class, first workgroup and first computer room
            school.class2 = NameDnObj(
                "{}-class2".format(school.name),
                self.create_school_class(
                    school.name,
                    class_name="class2",
                    description="Test class 2",
                    users=[school.student.dn, school.teacher.dn],
                )[1],
            )
            school.workgroup1 = NameDnObj(
                "{}-wg1".format(school.name),
                self.create_workgroup(
                    school.name,
                    workgroup_name="wg1",
                    description="Test workgroup",
                    users=[school.student.dn, school.teacher.dn],
                )[1],
            )
            school.room1 = NameDnObj(
                *self.create_computerroom(school.name, name="room1", description="Test room1")
            )


if __name__ == "__main__":
    with UCSTestSchool() as schoolenv:
        # create ou
        ou_name, ou_dn = schoolenv.create_ou(
            displayName=""
        )  # FIXME: displayName has been disabled for backward compatibility
        logger.info("NEW OU")
        logger.info("  %r", ou_name)
        logger.info("  %r", ou_dn)
        # create user
        user_name, user_dn = schoolenv.create_user(ou_name)
        logger.info("NEW USER")
        logger.info("  %r", user_name)
        logger.info("  %r", user_dn)
        # create user
        user_name, user_dn = schoolenv.create_user(ou_name, is_teacher=True)
        logger.info("NEW USER")
        logger.info("  %r", user_name)
        logger.info("  %r", user_dn)
        # create user
        user_name, user_dn = schoolenv.create_user(ou_name, is_staff=True)
        logger.info("NEW USER")
        logger.info("  %r", user_name)
        logger.info("  %r", user_dn)
        # create user
        user_name, user_dn = schoolenv.create_user(ou_name, is_teacher=True, is_staff=True)
        logger.info("NEW USER")
        logger.info("  %r", user_name)
        logger.info("  %r", user_dn)
