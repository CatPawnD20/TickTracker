from dotenv import load_dotenv
import os

load_dotenv()

mt5_login = os.getenv("MT5_LOGIN")
mt5_password = os.getenv("MT5_PASSWORD")
mt5_server = os.getenv("MT5_SERVER")
mt5_path = os.getenv("MT5_PATH")
mt5_symbol = os.getenv("MT5_SYMBOL")

postgres_host = os.getenv("POSTGRES_HOST")
postgres_user = os.getenv("POSTGRES_USER")
postgres_password = os.getenv("POSTGRES_PASSWORD")
postgres_database = os.getenv("POSTGRES_DATABASE")
