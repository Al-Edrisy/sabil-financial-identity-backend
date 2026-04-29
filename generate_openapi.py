import json
from app.main import app

schema = app.openapi()

with open("Sabil_Postman_Collection.json", "w") as f:
    json.dump(schema, f, indent=2)

print("Successfully generated Sabil_Postman_Collection.json")
