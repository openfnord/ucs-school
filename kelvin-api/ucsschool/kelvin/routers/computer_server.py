# from typing import List
#
# from fastapi import APIRouter, HTTPException, Query
# from pydantic import (
#     BaseModel,
#     Field,
#     HttpUrl,
#     Protocol,
#     PydanticValueError,
#     SecretStr,
#     StrBytes,
#     ValidationError,
#     validator,
# )
# from starlette.status import (
#     HTTP_200_OK,
#     HTTP_201_CREATED,
#     HTTP_204_NO_CONTENT,
#     HTTP_400_BAD_REQUEST,
#     HTTP_401_UNAUTHORIZED,
#     HTTP_404_NOT_FOUND,
# )
#
# from ucsschool.lib.models.computer import SchoolDC, SchoolDCSlave
#
# from ..utils import get_logger
#
# logger = get_logger(__name__)
# router = APIRouter()
#
#
# class ComputerServerModel(UcsSchoolBaseModel):
#     dn: str = None
#     name: str
#     school: HttpUrl
#     description: str = None
#
#
# @router.get("/")
# async def search(
#     name_filter: str = Query(
#         None,
#         title="List servers with this name. '*' can be used for an inexact search.",
#         min_length=3,
#     ),
#     school_filter: str = Query(
#         None,
#         title="List only servers in school with this name (not URL). ",
#         min_length=3,
#     ),
# ) -> List[ComputerServerModel]:
#     logger.debug(
#         "Searching for servers with: name_filter=%r school_filter=%r",
#         name_filter,
#         school_filter,
#     )
#     return [
#         ComputerServerModel(name="10a", school="https://foo.bar/schools/gsmitte"),
#         ComputerServerModel(name="8b", school="https://foo.bar/schools/gsmitte"),
#     ]
#
#
# @router.get("/{name}")
# async def get(name: str, school: str) -> ComputerServerModel:
#     return ComputerServerModel(name=name, school=f"https://foo.bar/schools/{school}")
#
#
# @router.post("/", status_code=HTTP_201_CREATED)
# async def create(server: ComputerServerModel) -> ComputerServerModel:
#     if server.name == "alsoerror":
#         raise HTTPException(
#             status_code=HTTP_400_BAD_REQUEST, detail="Invalid server name."
#         )
#     server.dn = "cn=foo,cn=computers,dc=test"
#     return server
#
#
# @router.patch("/{name}", status_code=HTTP_200_OK)
# async def partial_update(name: str, server: ComputerServerModel) -> ComputerServerModel:
#     if name != server.name:
#         logger.info("Renaming server from %r to %r.", name, server.name)
#     return server
#
#
# @router.put("/{name}", status_code=HTTP_200_OK)
# async def complete_update(
#     name: str, server: ComputerServerModel
# ) -> ComputerServerModel:
#     if name != server.name:
#         logger.info("Renaming server from %r to %r.", name, server.name)
#     return server
#
#
# @router.delete("/{name}", status_code=HTTP_204_NO_CONTENT)
# async def delete(name: str, request: Request) -> None:
#     async with UDM(**await udm_kwargs()) as udm:
#         sc = await get_lib_obj(udm, SchoolDC, name, None)
#         if await sc.exists(udm):
#             await sc.remove(udm)
#         else:
#             raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="TODO")
#     return None
