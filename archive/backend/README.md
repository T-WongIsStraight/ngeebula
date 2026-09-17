To run and test the FastAPI backend application locally, follow these steps:

1. Install Dependencies
Open your terminal or command prompt and install the required Python packages using pip:

Bash
pip install fastapi uvicorn sqlalchemy pydantic google-genai ortools
2. Set Your Gemini API Key
Since the app uses the google-genai SDK to generate natural-language schedule summaries, set your Gemini API key as an environment variable in your terminal:

On macOS / Linux:

Bash
export GEMINI_API_KEY="your_actual_api_key_here"
On Windows (Command Prompt):

DOS
set GEMINI_API_KEY=your_actual_api_key_here
On Windows (PowerShell):

PowerShell
$env:GEMINI_API_KEY="your_actual_api_key_here"
3. Organize Your Project Structure
Make sure your project files are saved in the same directory like this:

Plaintext
my_mrt_project/
├── database.py
├── solver.py
└── main.py
(Note: Ensure solver.py contains your solve_mrt_schedule function from your OR-Tools code).

4. Start the FastAPI Server
Navigate to your project directory in the terminal and launch the app using Uvicorn:

Bash
uvicorn main:app --reload
The --reload flag is useful because it automatically restarts the server whenever you save code changes.

5. Test the API Endpoints
Once the server is running, you can access it in two ways:

Interactive API Docs (Swagger UI):
Open your browser and go to:
http://127.0.0.1:8000/docs
From here, you can click on endpoints like /jobs/ or /schedule/run, click Try it out, fill in JSON data, and test them directly in your browser.

Connecting Streamlit (Marcus's Frontend):
When Marcus builds the Streamlit dashboard, he can point his API requests directly to [http://127.0.0.1:8000](http://127.0.0.1:8000) to fetch schedules, create jobs, and trigger Gemini summaries.
