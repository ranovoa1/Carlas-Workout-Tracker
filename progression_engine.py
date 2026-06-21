import json

with open("credentials.json", "r") as f:
    creds = json.load(f)

fields = ['type','project_id','private_key_id','private_key',
          'client_email','client_id','auth_uri','token_uri']

toml = "[gcp_service_account]\n"
for key in fields:
    if key in creds:
        val = creds[key].replace("\n", "\\n")
        toml += f'{key} = "{val}"\n'

with open("secrets.toml", "w") as f:
    f.write(toml)

print("Done! Open secrets.toml on your Desktop")