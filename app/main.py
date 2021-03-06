import os
from fastapi import FastAPI, Body, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId
from typing import Optional, List
import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient,AsyncIOMotorDatabase
import warnings
import sys
import uvicorn

# Required environment variables:
#   MONGODB_URI
#   MONGODB_URI_SRV
# Optional:
#   MONGODB_USERNAME
#   MONGODB_USERNAME


url = os.getenv("MONGODB_URL","<NOTSET>")
uri = os.getenv("MONGODB_URI","<NOTSET>")
uri_srv = os.getenv("MONGODB_URI_SRV","<NOTSET>")

if ((uri=="<NOTSET>") and  (uri_srv=="<NOTSET>")):
    warnings.warn("Did not detect MONGODB_URI or MONGODB_URI_SRV environment variables.")
    if (url=="<NOTSET>"):
        warnings.warn("Did not detect MONGODB_URL evironment variables.")
        warnings.warn("Please set these and relaunc the app.")
        warnings.warn(f"MONGODB_URI={uri}, MONGODB_URI_SRV={uri_srv}, MONOGDB_URL={url}")
        sys.exit(1)
    else:
        # Fall back to URL
        uri = url


if (uri_srv=="<NOTSET>"):
    warnings.warn("MONGODB_URI_SRV was not set.")
    uri = uri_srv

user = os.getenv("MONGODB_USERNAME","<NOTSET>")
pwd = os.getenv("MONGODB_PASSWORD","<NOTSET>")
pwd_redact = "<NOTSET>" if (pwd == "<NOTSET>") else "*REDACTED*"
print(f"uri:{uri}\nuri_srv:{uri_srv}\nuser:{user}\npwd:{pwd_redact}")


class DataBase:
    client: AsyncIOMotorClient = None
    petDB = None


db = DataBase()


async def connect_to_mongo():
    print("connecting to mongo...")
    if not "<NOTSET>" in {user,pwd}:
        try:
            db.client = motor.motor_asyncio.AsyncIOMotorClient(uri_srv,username=user,password=pwd)
        except Exception as err:
            warnings.warn(f"ERROR: {err}")
            if not uri == "<NOTSET>":
                warnings.warn(f"srv connect error, attepting with MONGODB_URI:{uri}")
                client = motor.motor_asyncio.AsyncIOMotorClient(uri,username=user,password=pwd)
    else:
        warnings.warn("MONGODB_USERNAME or MONGODB_PASSWORD not set, using connection string only.")
        try:
            db.client = motor.motor_asyncio.AsyncIOMotorClient(uri_srv)
        except Exception as err:
            warnings.warn(f"ERROR: {err}")
            if not uri == "<NOTSET>":
                warnings.warn(f"srv connect error, attepting with MONGODB_URI:{uri}")
                client = motor.motor_asyncio.AsyncIOMotorClient(uri)
    # get a collection
    # Format db.<database_name>.<collection_name>
    db.college = db.client.college
    print("connected to tancho_ci_db/pet")


async def close_mongo_connection():
    print("closing connection...")
    db.client.close()
    print("closed connection")



app = FastAPI()
app.add_event_handler("startup", connect_to_mongo)
app.add_event_handler("shutdown", close_mongo_connection)



#handler = Mangum(app)


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class StudentModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(...)
    email: EmailStr = Field(...)
    course: str = Field(...)
    gpa: float = Field(..., le=4.0)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "name": "Jane Doe",
                "email": "jdoe@example.com",
                "course": "Experiments, Science, and Fashion in Nanophotonics",
                "gpa": "3.0",
            }
        }


class UpdateStudentModel(BaseModel):
    name: Optional[str]
    email: Optional[EmailStr]
    course: Optional[str]
    gpa: Optional[float]

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "name": "Jane Doe",
                "email": "jdoe@example.com",
                "course": "Experiments, Science, and Fashion in Nanophotonics",
                "gpa": "3.0",
            }
        }


@app.post("/", response_description="Add new student", response_model=StudentModel)
async def create_student(student: StudentModel = Body(...)):
    student = jsonable_encoder(student)
    new_student = await db.college["students"].insert_one(student)
    created_student = await db.college["students"].find_one({"_id": new_student.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_student)


@app.get("/", response_description="Student API HealthCheck")
async def healthcheck():
    json_compatible_item_data = jsonable_encoder( { "Status": "OK", "Message": "Be sure to drink your Ovaltine", "Click": "<a href=\"docs\">docs</a>" } )
    return JSONResponse(content=json_compatible_item_data)

@app.get(
    "/students", response_description="List all students", response_model=List[StudentModel]
)

async def list_students():
    students = await db.college["students"].find().to_list(1000)
    #students = list(db.college["students"].find().limit(1000))
    print(f"students={students}")
    return students


@app.get(
    "/{id}", response_description="Get a single student", response_model=StudentModel
)
async def show_student(id: str):
    if (student := await db.college["students"].find_one({"_id": id})) is not None:
        return student

    raise HTTPException(status_code=404, detail=f"Student {id} not found")


@app.put("/{id}", response_description="Update a student", response_model=StudentModel)
async def update_student(id: str, student: UpdateStudentModel = Body(...)):
    student = {k: v for k, v in student.dict().items() if v is not None}

    if len(student) >= 1:
        update_result = await db.college["students"].update_one({"_id": id}, {"$set": student})

        if update_result.modified_count == 1:
            if (
                updated_student := await db.college["students"].find_one({"_id": id})
            ) is not None:
                return updated_student

    if (existing_student := await db.college["students"].find_one({"_id": id})) is not None:
        return existing_student

    raise HTTPException(status_code=404, detail=f"Student {id} not found")


@app.delete("/{id}", response_description="Delete a student")
async def delete_student(id: str):
    delete_result = await db.college["students"].delete_one({"_id": id})

    if delete_result.deleted_count == 1:
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail=f"Student {id} not found")


if __name__ == '__main__':
    uvicorn.run(app, port=8080, host='0.0.0.0')

