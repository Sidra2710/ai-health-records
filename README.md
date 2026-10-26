# AI Health Records

A Flask and SQLite application for managing patient blood-test records,
validating input, and requesting informational remarks from Google's Gemini API.

## Features

- Create, view, edit and delete patient records.
- Search records by patient name or email.
- Validate email addresses and dates of birth.
- Reject impossible dates and dates in the future.
- Validate numeric, non-negative blood-test values.
- Generate informational remarks using the Gemini API.
- Display clearer API errors, including timeout, quota and availability issues.
- Store records persistently in SQLite.

## Requirements

- Python 3.10 or newer
- Flask
- Requests
- A Google Gemini API key for AI features (optional)

## Run on Windows

Open PowerShell in the project folder.

Create a virtual environment:

    py -m venv .venv

Activate it:

    .\.venv\Scripts\Activate.ps1

Install dependencies:

    pip install -r requirements.txt

Set your Gemini API key if you want to use the AI feature:

    $env:GEMINI_API_KEY="YOUR_NEW_API_KEY"

Start the application:

    python app.py

Open this address in your browser:

    http://127.0.0.1:5000

## Configuration

GEMINI_API_KEY is read from the environment.
GEMINI_MODEL can optionally select a supported Gemini model.

Do not hardcode API keys in Python files or commit them to GitHub.
Do not commit patients.db, .env files, or virtual environments.

## Testing checklist

- Add a valid patient.
- Reject an invalid email address.
- Reject an impossible date such as 31/11/2001.
- Reject a future date of birth.
- Reject non-numeric or negative blood-test values.
- Search using a patient name.
- Search using an email address.
- Edit a patient and verify the saved changes.
- Delete a patient and verify the record is gone.
- Refresh AI remarks with a valid API key.
- Test the app without an API key.
- Check the displayed message when Gemini is unavailable.

## Medical disclaimer

This is a demonstration project, not a diagnostic tool.
AI-generated remarks may be incorrect and must not replace professional
medical advice. Clinical interpretation requires appropriate units,
laboratory reference ranges and patient context.