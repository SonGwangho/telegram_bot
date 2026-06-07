import os
from dotenv import load_dotenv

load_dotenv()

admin_user_id = os.getenv("admin_user_id")

telegram_token = os.getenv("telegram_token")
gemini_api_key = os.getenv("gemini_api_key")
gemini_model = os.getenv("gemini_model")
gemini_model_lite = os.getenv("gemini_model_lite")
gemini_data_file = os.getenv("gemini_data_file")
gemini_backup_dir = os.getenv("gemini_backup_dir")