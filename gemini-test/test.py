import os
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found!")

# Create Gemini client
client = genai.Client(api_key=api_key)

# Generate a response
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say hello to Jayasena in one sentence and say goodbye."
)

print(response.text)