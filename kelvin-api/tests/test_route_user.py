import random

import pytest
import requests
from pydantic import HttpUrl

import ucsschool.kelvin.constants
from ucsschool.kelvin.routers.role import SchoolUserRole
from ucsschool.kelvin.routers.user import UserCreateModel, UserModel, UserPatchModel
from ucsschool.lib.models.user import User
from udm_rest_client import UDM

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)


async def compare_lib_api_user(lib_user, api_user, udm, url_fragment):  # noqa: C901
    udm_obj = await lib_user.get_udm_object(udm)
    for key, value in api_user.dict().items():
        if key == "school":
            assert value.split("/")[-1] == getattr(lib_user, key)
        elif key == "schools":
            assert len(value) == len(getattr(lib_user, key))
            for entry in value:
                assert entry.split("/")[-1] in getattr(lib_user, key)
        elif key == "url":
            assert (
                api_user.unscheme_and_unquote(value)
                == f"{url_fragment}/users/{lib_user.name}"
            )
        elif key == "record_uid":
            assert value == udm_obj.props.ucsschoolRecordUID
        elif key == "source_uid":
            assert value == udm_obj.props.ucsschoolSourceUID
        elif key == "udm_properties":
            for key, value in value.items():
                assert value == getattr(udm_obj, key)
        elif key == "roles":
            api_roles = set([role.split("/")[-1] for role in value])
            lib_roles = set(
                [
                    SchoolUserRole.from_lib_role(role).value
                    for role in lib_user.ucsschool_roles
                ]
            )
            assert api_roles == lib_roles
        elif key == "birthday":
            if value:
                assert str(value) == getattr(lib_user, key)
            else:
                assert value == getattr(lib_user, key)
        else:
            assert value == getattr(lib_user, key)


@pytest.mark.asyncio
async def test_user_search(auth_header, url_fragment, create_random_users, udm_kwargs):
    create_random_users(
        {"student": 2, "teacher": 2, "staff": 2, "teachers_and_staff": 2}
    )
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, "DEMOSCHOOL")
        response = requests.get(
            f"{url_fragment}/users",
            headers=auth_header,
            params={"school_filter": "DEMOSCHOOL"},
        )
        api_users = {data["name"]: UserModel(**data) for data in response.json()}
        assert len(api_users.keys()) == len(lib_users)
        for lib_user in lib_users:
            api_user = api_users[lib_user.name]
            await compare_lib_api_user(lib_user, api_user, udm, url_fragment)


@pytest.mark.asyncio
async def test_user_get(auth_header, url_fragment, create_random_users, udm_kwargs):
    users = create_random_users(
        {"student": 2, "teacher": 2, "staff": 2, "teachers_and_staff": 2}
    )
    async with UDM(**udm_kwargs) as udm:
        for user in users:
            lib_users = await User.get_all(udm, "DEMOSCHOOL", f"username={user.name}")
            assert len(lib_users) == 1
            response = requests.get(
                f"{url_fragment}/users/{user.name}", headers=auth_header
            )
            assert type(response.json()) == dict
            api_user = UserModel(**response.json())
            await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)


@pytest.mark.asyncio
async def test_user_create(
    auth_header, url_fragment, create_random_user_data, udm_kwargs
):
    async with UDM(**udm_kwargs) as udm:
        r_user = create_random_user_data(roles=[f"{url_fragment}/roles/student"])
        lib_users = await User.get_all(udm, "DEMOSCHOOL", f"username={r_user.name}")
        assert len(lib_users) == 0
        response = requests.post(
            f"{url_fragment}/users/",
            headers={"Content-Type": "application/json", **auth_header},
            data=r_user.json(),
        )
        api_user = UserModel(**response.json())
        lib_users = await User.get_all(udm, "DEMOSCHOOL", f"username={r_user.name}")
        assert len(lib_users) == 1
        await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)
        requests.delete(
            f"{url_fragment}/users/{r_user.name}",
            headers=auth_header,
            data=r_user.json(),
        )


@pytest.mark.asyncio
async def test_user_put(
    auth_header, url_fragment, create_random_users, create_random_user_data, udm_kwargs
):
    users = create_random_users(
        {"student": 2, "teacher": 2, "staff": 2, "teachers_and_staff": 2}
    )
    async with UDM(**udm_kwargs) as udm:
        for user in users:
            new_user_data = create_random_user_data(roles=user.roles).dict()
            del new_user_data["name"]
            del new_user_data["record_uid"]
            del new_user_data["source_uid"]
            modified_user = UserCreateModel(**{**user.dict(), **new_user_data})
            response = requests.put(
                f"{url_fragment}/users/{user.name}",
                headers=auth_header,
                data=modified_user.json(),
            )
            assert response.status_code == 200
            api_user = UserModel(**response.json())
            lib_users = await User.get_all(udm, "DEMOSCHOOL", f"username={user.name}")
            assert len(lib_users) == 1
            await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)


@pytest.mark.asyncio
async def test_user_patch(
    auth_header, url_fragment, create_random_users, create_random_user_data, udm_kwargs
):
    users = create_random_users(
        {"student": 2, "teacher": 2, "staff": 2, "teachers_and_staff": 2}
    )
    async with UDM(**udm_kwargs) as udm:
        for user in users:
            new_user_data = create_random_user_data(roles=user.roles).dict()
            del new_user_data["name"]
            del new_user_data["record_uid"]
            del new_user_data["source_uid"]
            for key in random.sample(
                new_user_data.keys(), random.randint(1, len(new_user_data.keys()))
            ):
                del new_user_data[key]
            patch_user = UserPatchModel(**new_user_data)
            response = requests.patch(
                f"{url_fragment}/users/{user.name}",
                headers=auth_header,
                data=patch_user.json(),
            )
            assert response.status_code == 200
            api_user = UserModel(**response.json())
            lib_users = await User.get_all(udm, "DEMOSCHOOL", f"username={user.name}")
            assert len(lib_users) == 1
            await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)


@pytest.mark.asyncio
@pytest.mark.xfail
async def test_school_change(
    auth_header, url_fragment, create_random_users, create_random_schools, udm_kwargs
):
    schools = await create_random_schools(2)
    school1_dn, school1_attr = schools[0]
    school2_dn, school2_attr = schools[1]
    user = create_random_users(
        {"student": 1}, school=f"{url_fragment}/schools/{school1_attr['name']}"
    )[0]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(
            udm, school1_attr["name"], f"username={user.name}"
        )
        assert len(lib_users) == 1
        assert lib_users[0].school == school1_attr["name"]
        assert lib_users[0].schools == [school1_attr["name"]]
        patch_model = UserPatchModel(
            school=HttpUrl(f"{url_fragment}/schools/{school2_attr['name']}")
        )
        response = requests.patch(
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=patch_model.json(),
        )
        assert response.status_code == 200
        api_user = UserModel(**response.json())
        lib_users = await User.get_all(
            udm, school1_attr["name"], f"username={user.name}"
        )
        assert api_user.school == f"{url_fragment}/schools/{school2_attr['name']}"
        assert lib_users[0].school == school2_attr["name"]


@pytest.mark.asyncio
async def test_user_delete(
    auth_header, url_fragment, create_random_user_data, udm_kwargs
):
    async with UDM(**udm_kwargs) as udm:
        r_user = create_random_user_data(roles=[f"{url_fragment}/roles/student"])
        lib_users = await User.get_all(udm, "DEMOSCHOOL", f"username={r_user.name}")
        assert len(lib_users) == 0
        response = requests.post(
            f"{url_fragment}/users/",
            headers={"Content-Type": "application/json", **auth_header},
            data=r_user.json(),
        )
        assert response.status_code == 201
        lib_users = await User.get_all(udm, "DEMOSCHOOL", f"username={r_user.name}")
        assert len(lib_users) == 1
        response = requests.delete(
            f"{url_fragment}/users/{r_user.name}",
            headers=auth_header,
            data=r_user.json(),
        )
        assert response.status_code == 204
        lib_users = await User.get_all(udm, "DEMOSCHOOL", f"username={r_user.name}")
        assert len(lib_users) == 0
        response = requests.delete(
            f"{url_fragment}/users/NON_EXISTENT_USER",
            headers=auth_header,
            data=r_user.json(),
        )
        assert response.status_code == 404
