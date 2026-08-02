from datetime import datetime
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Flask, flash, get_flashed_messages, redirect, render_template_string, request, session, url_for

# Create the Flask web app. This is the main entry point for the tracker.
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# In-memory placeholder storage. Replace this with a real database later.
# Each activity is stored as a dictionary so the UI can show details like name, date, distance, and source.
activity_items = []
goal_items = []

# Strava integration settings. These are used for OAuth login and uploading activities.
STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID', '260628')
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET', '87e49e77589f4ff35de2472bd4820b1af8fe347b')
STRAVA_REDIRECT_URI = os.environ.get('STRAVA_REDIRECT_URI', 'https://milestones-ktz9.onrender.com/strava/callback')
STRAVA_AUTH_URL = 'https://www.strava.com/oauth/authorize'
STRAVA_TOKEN_URL = 'https://www.strava.com/api/v3/oauth/token'
STRAVA_API_URL = 'https://www.strava.com/api/v3'


def is_strava_configured():
    """Return True when the Strava app credentials are available."""
    return bool(STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET)


def build_strava_auth_url():
    """Build the Strava OAuth URL and save a security token in the session."""
    state = secrets.token_hex(16)
    session['strava_oauth_state'] = state
    params = {
        'client_id': STRAVA_CLIENT_ID,
        'redirect_uri': STRAVA_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'activity:read_all,activity:write',
        'state': state,
    }
    return f"{STRAVA_AUTH_URL}?{urlencode(params)}"


def upload_activity_to_strava(access_token, name):
    """Send a new workout to Strava using the user's access token."""
    payload = {
        'name': name,
        'type': 'Run',
        'start_date_local': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'elapsed_time': 1800,
        'distance': 5000,
        'description': 'Uploaded from the Milestones shell',
    }
    return requests.post(
        f'{STRAVA_API_URL}/activities',
        headers={'Authorization': f'Bearer {access_token}'},
        data=payload,
        timeout=30,
    )


def fetch_strava_activities(access_token):
    """Fetch the latest Strava activities for the signed-in athlete."""
    response = requests.get(
        f'{STRAVA_API_URL}/athlete/activities',
        headers={'Authorization': f'Bearer {access_token}'},
        params={'per_page': 10},
        timeout=30,
    )
    if not response.ok:
        flash(f'Unable to fetch Strava activities: {response.status_code} {response.text[:120]}', 'danger')
        return []

    return response.json()


def calculate_pace_minutes_per_mile(average_speed_mps):
    """Convert Strava's average speed in meters/second to a pace in minutes per mile."""
    try:
        average_speed_mps = float(average_speed_mps)
    except (TypeError, ValueError):
        return None

    if average_speed_mps <= 0:
        return None

    miles_per_hour = average_speed_mps * 2.2369362920544
    return round(60 / miles_per_hour, 2)


def format_pace_minutes_per_mile(average_speed_mps):
    """Format pace as mm:ss/mi for display in the UI."""
    pace_value = calculate_pace_minutes_per_mile(average_speed_mps)
    if pace_value is None:
        return None

    whole_minutes = int(pace_value)
    seconds = int(round((pace_value - whole_minutes) * 60))
    if seconds == 60:
        whole_minutes += 1
        seconds = 0

    return f'{whole_minutes}:{seconds:02d}/mi'


def page(title, body):
    """Render the shared page shell with navigation, flash messages, and theme support."""
    messages = ''.join(
        f'<p class="{category}">{message}</p>'
        for category, message in get_flashed_messages(with_categories=True)
    )
    dark_mode = 'dark' if session.get('dark_mode') else 'light'
    return render_template_string('''
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{{ title }}</title>
            <link rel="stylesheet" href="/static/css/styles.css">
          </head>
          <body class="theme-{{ dark_mode }}">
            <div class="page-shell">
              <div class="topbar">
                <h1 class="page-title">Milestones</h1>
                <form method="post" action="/theme/toggle" class="theme-toggle-form">
                  <button type="submit" class="theme-toggle-btn">
                    {{ 'Light mode' if dark_mode == 'dark' else 'Dark mode' }}
                  </button>
                </form>
              </div>
              <nav>
                <a href="/">Home</a> |
                <a href="/dashboard">Dashboard</a> |
                <a href="/activities">Activities</a> |
                <a href="/goals">Goals</a> |
                <a href="/milestones">Milestones</a> |
                <a href="/profile">Profile</a>
              </nav>
              <hr>
              {{ messages | safe }}
              {{ body | safe }}
            </div>
          </body>
        </html>
    ''', title=title, body=body, messages=messages, dark_mode=dark_mode)


@app.route('/')
def home():
    """Show the landing page for the Milestones app."""
    body = '''
        <p>This is a stripped-down shell for your Milestones app.</p>
        <p>Use this file to add the real pieces one by one.</p>
    '''
    return page('Home', body)


@app.route('/dashboard')
def dashboard():
    """Show the dashboard placeholder for future stats and summaries."""
    body = '''
        <p>Dashboard placeholder.</p>
        <p>TODO: calculate totals, weekly trends, and recent activity summaries here.</p>
    '''
    return page('Dashboard', body)


@app.route('/milestones')
def milestones():
    """Show the milestones section for progress tracking."""
    body = '''
        <section class="panel">
          <div class="section-title">Milestones</div>
          <p>Track your progress milestones here.</p>
        </section>
    '''
    return page('Milestones', body)


@app.route('/activities', methods=['GET', 'POST'])
def activities():
    """Handle activity creation, deletion, and optional Strava syncing."""
    # When the form is submitted, save the new activity and optionally upload it to Strava.
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'delete' and request.form.get('activity_index') is not None:
            try:
                index = int(request.form.get('activity_index'))
            except ValueError:
                index = -1
            if 0 <= index < len(activity_items):
                del activity_items[index]
                flash('Activity removed.', 'info')
            return redirect(url_for('activities'))

        name = request.form.get('name', '').strip() or 'Workout'
        activity_type = request.form.get('type', 'Run').strip() or 'Run'
        distance = request.form.get('distance', '0').strip() or '0'
        duration = request.form.get('duration', '').strip() or '0'
        upload_requested = request.form.get('upload_to_strava') == '1'

        try:
            distance_value = float(distance)
        except ValueError:
            distance_value = 0.0

        activity_items.append({
            'name': name,
            'type': activity_type,
            'start_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
            'distance': round(distance_value, 2),
            'duration': duration,
            'source': 'local',
            'strava_id': None,
        })

        if upload_requested and 'strava_access_token' in session:
            response = upload_activity_to_strava(session['strava_access_token'], name)
            if response.ok:
                flash('Saved locally and uploaded to Strava.', 'success')
            else:
                flash(f'Saved locally, but Strava upload failed: {response.text[:120]}', 'warning')
        else:
            if upload_requested:
                flash('Saved locally. Connect Strava first to upload.', 'info')
            else:
                flash('Saved locally.', 'info')

        return redirect(url_for('activities'))

    # When the page loads, show the activity form and any Strava-connected activities.
    strava_connected = 'strava_access_token' in session
    if strava_connected:
        for item in fetch_strava_activities(session['strava_access_token']):
            strava_id = item.get('id')
            if any(act.get('strava_id') == strava_id for act in activity_items if act.get('strava_id') is not None):
                continue
            activity_items.append({
                'name': item.get('name') or 'Strava activity',
                'type': item.get('type', 'Run'),
                'start_date': item.get('start_date_local', '').replace('T', ' '),
                'distance': round(item.get('distance', 0) / 1609.34, 2),
                'source': 'strava',
                'strava_id': strava_id,
                'pace_text': format_pace_minutes_per_mile(item.get('average_speed')),
            })

    rows = []
    for index, item in enumerate(activity_items):
        activity_name = item.get('name', 'Workout')
        activity_type = item.get('type', 'Run')
        activity_date = item.get('start_date', 'Unknown date')
        distance = item.get('distance', 0)
        duration = item.get('duration', 'n/a')
        source = item.get('source', 'local')
        pace_text = item.get('pace_text')

        meta_items = [
            f'<span>Date: {activity_date}</span>',
            f'<span>Distance: {distance} mi</span>',
            f'<span>Duration: {duration} min</span>',
            f'<span>Source: {source}</span>',
        ]
        if pace_text:
            meta_items.append(f'<span>Pace: {pace_text}</span>')

        rows.append(f"""
            <div class="activity-card">
              <div class="activity-card__top">
                <strong>{activity_name}</strong>
                <span class="activity-tag">{activity_type}</span>
              </div>
              <div class="activity-card__meta">
                {''.join(meta_items)}
              </div>
              <form method="post" class="activity-card__actions">
                <input type="hidden" name="activity_index" value="{index}">
                <input type="hidden" name="action" value="delete">
                <button type="submit">Delete</button>
              </form>
            </div>
        """)

    connect_link = '<a href="/strava/connect">Connect Strava</a>' if not strava_connected else '<a href="/strava/disconnect">Disconnect Strava</a>'
    sync_link = '<a href="/strava/sync">Sync from Strava</a>' if strava_connected else ''

    body = f'''
        <section class="panel">
          <h2>Add an activity</h2>
          <form method="post" class="activity-form">
            <label>
              Name
              <input type="text" name="name" placeholder="Morning run" required>
            </label>
            <label>
              Type
              <input type="text" name="type" value="Run">
            </label>
            <label>
              Distance (mi)
              <input type="number" name="distance" step="0.1" value="5">
            </label>
            <label>
              Duration (min)
              <input type="number" name="duration" step="1" value="30">
            </label>
            <label class="checkbox-row">
              <input type="checkbox" name="upload_to_strava" value="1">
              Upload to Strava
            </label>
            <button type="submit">Save activity</button>
          </form>
        </section>

        <section class="panel panel--tight">
          <div class="activity-toolbar">
            <h2>Recent activities</h2>
            <div>
              {connect_link}
              {sync_link}
            </div>
          </div>
          <div class="activity-list">
            {''.join(rows) if rows else '<p class="empty-state">No activities yet.</p>'}
          </div>
        </section>
    '''
    return page('Activities', body)


@app.route('/goals')
def goals():
    """Show the current goals list. This is still a simple placeholder."""
    rows = ''.join(
        f'<li>{item}</li>' for item in goal_items
    ) or '<li>No goals yet.</li>'

    body = f'''
        <ul>{rows}</ul>
        <p>TODO: add goal creation, progress tracking, and completion logic here.</p>
    '''
    return page('Goals', body)


@app.route('/profile')
def profile():
    """Show the user profile page and Strava connection status."""
    strava_status = 'Connected' if 'strava_access_token' in session else 'Not connected'
    body = f'''
        <p>Profile placeholder.</p>
        <p>Strava status: {strava_status}</p>
        <p>TODO: add account info, authentication, and optional Strava connection here.</p>
    '''
    return page('Profile', body)


@app.route('/strava/connect')
def strava_connect():
    """Start the Strava authorization flow for the current user."""
    if not is_strava_configured():
        flash('Strava integration is not configured yet. Add STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET.', 'warning')
        return redirect(url_for('profile'))

    return redirect(build_strava_auth_url())


@app.route('/strava/callback')
def strava_callback():
    """Handle the OAuth callback returned by Strava after login."""
    error = request.args.get('error')
    if error:
        flash(f'Strava authorization failed: {error}', 'danger')
        return redirect(url_for('profile'))

    code = request.args.get('code')
    state = request.args.get('state')
    if not code or not state or session.get('strava_oauth_state') != state:
        flash('Invalid Strava callback.', 'danger')
        return redirect(url_for('profile'))

    response = requests.post(STRAVA_TOKEN_URL, data={
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
    }, timeout=30)

    if not response.ok:
        flash('Could not exchange the Strava code for an access token.', 'danger')
        return redirect(url_for('profile'))

    data = response.json()
    session['strava_access_token'] = data.get('access_token')
    session['strava_refresh_token'] = data.get('refresh_token')
    session['strava_athlete_id'] = data.get('athlete', {}).get('id')
    session.pop('strava_oauth_state', None)
    flash('Strava connected successfully.', 'success')
    return redirect(url_for('activities'))


@app.route('/strava/sync')
def strava_sync():
    """Pull new activities from Strava into the local tracker list."""
    if 'strava_access_token' not in session:
        flash('Connect Strava first before syncing activities.', 'warning')
        return redirect(url_for('activities'))

    fetched = fetch_strava_activities(session['strava_access_token'])
    count = 0
    for item in fetched:
        strava_id = item.get('id')
        if any(act.get('strava_id') == strava_id for act in activity_items if act.get('strava_id') is not None):
            continue

        activity_items.append({
            'name': item.get('name') or 'Strava activity',
            'type': item.get('type', 'Run'),
            'start_date': item.get('start_date_local', '').replace('T', ' '),
            'distance': round(item.get('distance', 0) / 1609.34, 2),
            'source': 'strava',
            'strava_id': strava_id,
            'pace_text': format_pace_minutes_per_mile(item.get('average_speed')),
        })
        count += 1

    flash(f'Synced {count} activities from Strava.', 'success' if count else 'info')
    return redirect(url_for('activities'))


@app.route('/strava/disconnect')
def strava_disconnect():
    """Remove the Strava connection details from the current session."""
    session.pop('strava_access_token', None)
    session.pop('strava_refresh_token', None)
    session.pop('strava_athlete_id', None)
    session.pop('strava_oauth_state', None)
    flash('Strava disconnected.', 'info')
    return redirect(url_for('activities'))


@app.route('/theme/toggle', methods=['POST'])
def toggle_theme():
    """Switch between light and dark mode for the current session."""
    session['dark_mode'] = not session.get('dark_mode', False)
    return redirect(request.referrer or url_for('home'))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

