#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: check password generation code
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - python-ucs-school
## bugs: [45640]

import string

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
import univention.testing.utils as utils
from ucsschool.lib.models.utils import create_passwd

default_length = 8
default_specials = "$%&*-+=:.?"
forbidden_chars = ["i", "I", "l", "L", "o", "O", "0", "1"]
pw_count = 0


def create_pw(length, specials, num_specials_allowed):
    global pw_count
    cpw_kwargs = {"length": length, "dn": None}
    if specials is not None:
        cpw_kwargs["specials"] = specials

    pw = create_passwd(**cpw_kwargs)
    pw_count += 1
    if len(pw) != length:
        utils.fail(
            "Requested password of length {}, got {!r} with length {}.".format(length, pw, len(pw))
        )
    check_num_specials(pw, specials, num_specials_allowed)
    check_forbidden_chars(pw)
    check_char_classes(pw, specials if specials is not None else default_specials)


def check_pw_policy():
    global pw_count

    with udm_test.UCSTestUDM() as udm, ucr_test.UCSTestConfigRegistry() as ucr:
        for length in range(1, 21):
            policy_dn = udm.create_object(
                "policies/pwhistory",
                position="cn=pwhistory,cn=users,cn=policies,{}".format(ucr["ldap/base"]),
                name=uts.random_name(),
                pwLength=length,
            )
            user_dn, username = udm.create_user(
                policy_reference=policy_dn, password=uts.random_string(length)
            )
            pw = create_passwd(dn=user_dn)
            pw_count += 1
            if len(pw) != length:
                utils.fail(
                    "Generated password for DN {!r} is {!r} with length {}, but should have been"
                    " {}.".format(user_dn, pw, len(pw), length)
                )
            check_num_specials(pw)
            check_forbidden_chars(pw)
            check_char_classes(pw, default_specials)


def check_num_specials(pw, specials=None, num_specials_allowed=None):
    specials = default_specials if specials is None else specials
    forbidden_specials = set(default_specials) - set(specials)
    num_specials_allowed = len(pw) / 5 if num_specials_allowed is None else num_specials_allowed

    num_specials = 0
    for char in pw:
        if char in forbidden_specials:
            utils.fail(
                "Password {!r} with length {} contains a special that was not requested (argument "
                "specials={!r}): "
                "{!r}".format(pw, len(pw), specials, char)
            )
        if char in specials:
            num_specials += 1
    if num_specials > num_specials_allowed:
        utils.fail(
            "Password {!r} with length {} contains {} specials, but only {} are allowed.".format(
                pw, len(pw), num_specials, num_specials_allowed
            )
        )


def check_char_classes(pw, specials):
    if not any(char in (string.lowercase + string.uppercase) for char in pw):
        utils.fail(
            "Password {!r} with length {} does not contain any lowercase or uppercase character.".format(
                pw, len(pw)
            )
        )

    if len(pw) >= 4:
        if not any(char in string.lowercase for char in pw):
            utils.fail(
                "Password {!r} with length {} does not contain lowercase character.".format(pw, len(pw))
            )

        if not any(char in string.uppercase for char in pw):
            utils.fail(
                "Password {!r} with length {} does not contain uppercase character.".format(pw, len(pw))
            )

        if not any(char in string.digits for char in pw):
            utils.fail("Password {!r} with length {} does not contain digit.".format(pw, len(pw)))

        if specials != "" and len(pw) / 5 > 0:
            if not any(char in specials for char in pw):
                utils.fail(
                    "Password {!r} with length {} does not specials (argument specials={!r}).".format(
                        pw, len(pw), specials
                    )
                )


def check_forbidden_chars(pw):
    for char in pw:
        if char in forbidden_chars:
            utils.fail(
                "Password {!r} with length {} contains forbidden character {!r}.".format(
                    pw, len(pw), char
                )
            )


def main():
    global pw_count

    print("Checking default password length...")
    pw = create_passwd()
    pw_count += 1
    if len(pw) != default_length:
        utils.fail(
            "Requested password of length {}, got {!r} with length {}.".format(
                default_length, pw, len(pw)
            )
        )
    check_num_specials(pw)
    check_forbidden_chars(pw)

    print("Checking password length 0...")
    try:
        pw = create_passwd(0)
        utils.fail("Requested password of length 0, got {!r} with length {}.".format(pw, len(pw)))
    except AssertionError:
        pass

    for length in range(1, 21):
        print("Checking password length {}...".format(length))
        for _x in range(100):
            create_pw(length, None, None)
            create_pw(length, "", 0)
            create_pw(length, "@#~", None)

    print("Checking password policy...")
    check_pw_policy()

    print("Checked {} passwords.".format(pw_count))


if __name__ == "__main__":
    main()
