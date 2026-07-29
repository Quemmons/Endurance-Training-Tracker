Local development URL

- Website link (pinned): http://localhost:5002

Strava OAuth callback (for local testing):

- Redirect URI: http://localhost:5002/strava/callback

If you expose the app publicly (ngrok or deployed), set the Redirect URI in Strava to the public URL + `/strava/callback`.

Run the app (from the project root):

```bash
# make sure your venv is created (python -m venv .venv) and dependencies installed
# then run:
./run.sh
```

Notes:
- The `run.sh` script explicitly starts the Flask dev server on port 5002 so the URL above will not change unless you edit the script.
- If you need the app accessible on your LAN, change the script to `flask run --host=0.0.0.0 --port=5002`.
