from dotenv import dotenv_values

env = dotenv_values("env/.env")
print(env)
print(env["USER_ID"])
