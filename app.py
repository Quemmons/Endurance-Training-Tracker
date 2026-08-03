from datetime import datetime
import os
import secrets
from hashlib import sha256
from urllib.parse import urlencode

import requests
from flask import (
    Flask,
    flash,
    get_flashed_messages,
    redirect,
    render_template,
    render_template_string,
    request,
    session,
    url_for,
)

# Create the Flask app that serves the Milestones experience.
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['JSON_SORT_KEYS'] = False

# App flow overview:
# - / shows the landing page
# - /login and /register handle authentication
# - /dashboard, /activities, /goals, /milestones, and /profile are the main app pages
# - /strava/* handles optional Strava integration and activity syncing

# In-memory data stores used by the demo app.
# Activities and goals are stored per user so one account cannot see another account's data.
activity_items = []
goal_items = []
users = {}
user_data = {}


def get_user_store():
    """Return the data bucket for the current session, creating one when needed."""
    user_key = session.get('username') or session.get('guest_id')
    if not user_key:
        user_key = secrets.token_hex(8)
        session['guest_id'] = user_key

    if user_key not in user_data:
        user_data[user_key] = {'activities': [], 'goals': []}

    return user_data[user_key]

# Strava integration settings used for OAuth login and activity syncing.
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
    """Build the Strava OAuth URL and store a state token in the session."""
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


def fetch_strava_activities(access_token):
    """Fetch the latest Strava activities for the signed-in athlete."""
    response = requests.get(
        f'{STRAVA_API_URL}/athlete/activities',
        headers={'Authorization': f'Bearer {access_token}'},
        params={'per_page': 10},
        timeout=30,
    )
    if response.status_code == 401:
        session.pop('strava_access_token', None)
        session.pop('strava_refresh_token', None)
        session.pop('strava_athlete_id', None)
        flash('Your Strava connection has expired. Please reconnect Strava to sync activities.', 'warning')
        return []

    if not response.ok:
        flash(f'Unable to fetch Strava activities: {response.status_code} {response.text[:120]}', 'danger')
        return []

    return response.json()


def format_activity_start_date(timestamp):
    """Format a Strava or local timestamp as YYYY-MM-DD h:mm AM/PM."""
    if not timestamp:
        return ''

    iso_text = timestamp
    if iso_text.endswith('Z'):
        iso_text = iso_text[:-1] + '+00:00'

    try:
        dt = datetime.fromisoformat(iso_text)
    except ValueError:
        dt = None

    if dt is None:
        return timestamp.replace('T', ' ').rstrip('Z')

    date_part = dt.strftime('%Y-%m-%d')
    hour = dt.strftime('%I').lstrip('0') or '0'
    minute = dt.strftime('%M')
    ampm = dt.strftime('%p')
    return f'{date_part} {hour}:{minute} {ampm}'


def format_duration_seconds(seconds):
    """Render a duration as H:MM:SS."""
    try:
        total_seconds = int(float(seconds))
    except (TypeError, ValueError):
        return None

    if total_seconds < 0:
        total_seconds = 0

    hours = total_seconds // 3600
    remainder = total_seconds % 3600
    minutes = remainder // 60
    secs = remainder % 60
    return f'{hours}:{minutes:02d}:{secs:02d}'


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


def build_dashboard_stats(store):
    """Build a small summary payload for the dashboard view."""
    activities = store.get('activities', [])
    total_distance = sum(float(item.get('distance', 0) or 0) for item in activities)
    total_by_type = {'run': 0.0, 'bike': 0.0, 'swim': 0.0}
    recent = []

    for item in activities:
        activity_type = (item.get('type') or 'Run').lower()
        if activity_type.startswith('bike') or activity_type == 'ride':
            activity_type = 'bike'
        elif activity_type.startswith('swim'):
            activity_type = 'swim'
        else:
            activity_type = 'run'

        total_by_type[activity_type] += float(item.get('distance', 0) or 0)
        recent.append({
            'name': item.get('name', 'Workout'),
            'type': activity_type,
            'distance': item.get('distance', 0),
            'date': item.get('start_date', ''),
            'source': item.get('source', 'local'),
        })

    recent = recent[-5:][::-1]
    workout_count = len(activities)
    average_pace = None
    pace_values = [item.get('pace_text') for item in activities if item.get('pace_text')]
    if pace_values:
        try:
            pace_numbers = [float(value.split('/')[0].split(':')[0]) + float(value.split('/')[0].split(':')[1]) / 60 for value in pace_values if ':' in value]
            average_pace = round(sum(pace_numbers) / len(pace_numbers), 2)
        except (ValueError, IndexError):
            average_pace = None

    return {
        'total_distance': round(total_distance, 2),
        'total_by_type': {key: round(value, 2) for key, value in total_by_type.items()},
        'workout_count': workout_count,
        'average_pace': average_pace,
        'recent': recent,
    }


def build_funny_stats(store):
    """Create placeholder funny stats for the dashboard."""
    activities = store.get('activities', [])
    total_distance = sum(float(item.get('distance', 0) or 0) for item in activities)
    return [
        {
            'title': 'School bus lengths run',
            'value': round(total_distance / 45, 1),
            'detail': 'A school bus is about 45 feet long.',
        },
        {
            'title': 'Marathons completed',
            'value': round(total_distance / 26.2, 1),
            'detail': 'Because every training log deserves a dramatic comparison.',
        },
        {
            'title': 'Coffee-fueled miles',
            'value': round(total_distance / 10, 1),
            'detail': 'A very optimistic estimate for your pace.',
        },
    ]


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
    """Render the landing page for the Milestones app."""
    return render_template('home.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Render the login page and authenticate a registered user."""
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        stored_user = users.get(username)

        if stored_user and stored_user['password_hash'] == sha256(password.encode('utf-8')).hexdigest():
            session.clear()
            session['user_id'] = username
            session['username'] = username
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))

        flash('Invalid username or password.', 'danger')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Render the registration page and create a new user account."""
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        if not username or not password:
            flash('Please provide both a username and password.', 'danger')
            return redirect(url_for('register'))

        if username in users:
            flash('That username is already taken.', 'danger')
            return redirect(url_for('register'))

        users[username] = {
            'username': username,
            'password_hash': sha256(password.encode('utf-8')).hexdigest(),
        }
        user_data[username] = {
            'activities': [],
            'goals': [],
        }
        session.clear()
        session['user_id'] = username
        session['username'] = username
        flash('Registration successful. You are now signed in.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    """Clear the current session and return the user to the home page."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard():
    """Show a dashboard with summaries, funny stats, and recent activity history."""
    store = get_user_store()
    stats = build_dashboard_stats(store)
    funny_stats = build_funny_stats(store)
    return render_template('dashboard.html', stats=stats, funny_stats=funny_stats, goals=store.get('goals', []))


@app.route('/milestones')
def milestones():
    """Redirect the old milestones route to the dashboard so the app has one home for stats."""
    return redirect(url_for('dashboard'))


@app.route('/activities', methods=['GET', 'POST'])
def activities():
    """Handle adding, deleting, and displaying activities."""
    store = get_user_store()
    user_activities = store['activities']

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'delete' and request.form.get('activity_index') is not None:
            try:
                index = int(request.form.get('activity_index'))
            except ValueError:
                index = -1
            if 0 <= index < len(user_activities):
                del user_activities[index]
                flash('Activity removed.', 'info')
            return redirect(url_for('activities'))

        if request.form.get('name'):
            user_activities.append({
                'name': request.form.get('name'),
                'type': request.form.get('type', 'Run'),
                'start_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                'distance': 0,
                'duration_seconds': 0,
                'source': 'local',
            })
            flash('Activity added.', 'success')
            return redirect(url_for('activities'))

    # When the page loads, show Strava-connected activities and the recent activity list.
    strava_connected = 'strava_access_token' in session
    if not strava_connected and not user_activities:
        flash('Tip: connect Strava on the activities page to sync your training history.', 'info')
    if strava_connected:
        for item in fetch_strava_activities(session['strava_access_token']):
            strava_id = item.get('id')
            if any(act.get('strava_id') == strava_id for act in user_activities if act.get('strava_id') is not None):
                continue
            raw_start = item.get('start_date_local', '')
            duration_seconds = item.get('moving_time', item.get('elapsed_time', 0)) or 0
            user_activities.append({
                'name': item.get('name') or 'Strava activity',
                'type': item.get('type', 'Run'),
                'start_date': format_activity_start_date(raw_start),
                'distance': round(item.get('distance', 0) / 1609.34, 2),
                'duration_seconds': duration_seconds,
                'source': 'strava',
                'strava_id': strava_id,
                'pace_text': format_pace_minutes_per_mile(item.get('average_speed')),
            })

    rows = []
    for index, item in enumerate(user_activities):
        activity_name = item.get('name', 'Workout')
        activity_type = item.get('type', 'Run')
        activity_date = item.get('start_date', 'Unknown date')
        distance = item.get('distance', 0)
        duration_text = format_duration_seconds(item.get('duration_seconds')) or 'n/a'
        source = item.get('source', 'local')
        pace_text = item.get('pace_text')

        meta_items = [
            f'<span>Date: {activity_date}</span>',
            f'<span>Distance: {distance} mi</span>',
            f'<span>Duration: {duration_text}</span>',
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


@app.route('/goals', methods=['GET', 'POST'], endpoint='view_goals')
def goals():
    """Show the current goals list and allow creating new goals."""
    store = get_user_store()
    user_goals = store['goals']

    if request.method == 'POST':
        goal_type = (request.form.get('goal_type') or '').strip().lower()
        target_value = request.form.get('target_value', '').strip()
        start_date = request.form.get('start_date', '').strip()
        end_date = request.form.get('end_date', '').strip()
        description = (request.form.get('description') or '').strip()

        if not goal_type or not target_value or not start_date or not end_date:
            flash('Please fill in all goal fields.', 'danger')
            return redirect(url_for('view_goals'))

        try:
            target_value = float(target_value)
        except ValueError:
            flash('Target value must be a number.', 'danger')
            return redirect(url_for('view_goals'))

        user_goals.append({
            'id': secrets.token_hex(6),
            'goal_type': goal_type,
            'target_value': target_value,
            'current_progress': 0.0,
            'start_date': start_date,
            'end_date': end_date,
            'description': description or f'{goal_type.capitalize()} goal',
        })
        flash('Goal created.', 'success')
        return redirect(url_for('view_goals'))

    return render_template('goals.html', goals=user_goals)


@app.route('/profile')
def profile():
    """Show the user profile page and current Strava connection status."""
    username = session.get('username') or 'Athlete'
    created_at = datetime.utcnow().strftime('%Y-%m-%d')
    strava_connected = 'strava_access_token' in session
    strava_configured = is_strava_configured()
    return render_template('profile.html', username=username, created_at=created_at, strava_connected=strava_connected, strava_configured=strava_configured)


@app.route('/strava/connect')
def strava_connect():
    """Start the Strava authorization flow for the current user."""
    if not is_strava_configured():
        flash('Strava integration is not configured yet. Add STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET.', 'warning')
        return redirect(url_for('profile'))

    return redirect(build_strava_auth_url())


@app.route('/strava/callback')
def strava_callback():
    """Handle the Strava OAuth callback after the user authorizes the app."""
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

    store = get_user_store()
    user_activities = store['activities']
    fetched = fetch_strava_activities(session['strava_access_token'])
    count = 0
    for item in fetched:
        strava_id = item.get('id')
        if any(act.get('strava_id') == strava_id for act in user_activities if act.get('strava_id') is not None):
            continue

        user_activities.append({
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

