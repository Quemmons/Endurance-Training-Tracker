from datetime import datetime, timedelta
import random
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
        user_data[user_key] = {'activities': [], 'goals': [], 'year_to_date_miles': None, 'next_activity_seq': 1}

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


def normalize_activity_type(activity_type):
    """Normalize all activities to the running-only category used by the app."""
    return 'run'


def next_activity_seq(store):
    """Return the next sequence number for a new activity and advance the counter."""
    seq = store.get('next_activity_seq', 1)
    store['next_activity_seq'] = seq + 1
    return seq


def is_run_activity(activity):
    """Return True when a Strava activity should be imported into the running tracker."""
    activity_type = (activity or {}).get('type', 'Run')
    return str(activity_type).strip().lower() == 'run'


def get_yearly_total(store):
    """Return the effective yearly mileage total.

    If a manual year-to-date baseline has been set, the total is that baseline
    plus the distance of any activities added *after* the baseline was entered
    (tracked by sequence number, not clock time, so it isn't affected by
    minute-level timestamp precision or activity deletions). Before a baseline
    is set, this is simply the sum of all logged activity distance.
    """
    activities = store.get('activities', [])
    baseline = store.get('year_to_date_miles')
    baseline_seq = store.get('year_to_date_miles_baseline_seq')

    if baseline is not None and baseline_seq is not None:
        added_since = sum(
            float(item.get('distance', 0) or 0)
            for item in activities
            if item.get('seq', 0) > baseline_seq
        )
        return round(float(baseline) + added_since, 2)

    activity_total = sum(float(item.get('distance', 0) or 0) for item in activities)
    return round(activity_total, 2)

def get_weekly_total(store):
    """Return miles run in the last 7 days."""
    total = 0

    for activity in store.get("activities", []):
        try:
            date = datetime.strptime(activity["start_date"][:10], "%Y-%m-%d")
            if date >= datetime.now() - timedelta(days=7):
                total += float(activity.get("distance", 0))
        except:
            pass

    return round(total, 2)


def get_last_run(store):
    """Return the distance of the most recent run."""
    activities = store.get("activities", [])
    if not activities:
        return 0
    return float(activities[-1].get("distance", 0))

def update_goal_progress(store):
    """Refresh each goal's progress based on the shared yearly mileage total."""
    yearly_total = get_yearly_total(store)
    for goal in store.get('goals', []):
        goal['current_progress'] = round(float(yearly_total), 2)
        target = float(goal.get('target_value') or 0)
        if target > 0:
            percent = (goal['current_progress'] / target) * 100
        else:
            percent = 0
        goal['progress_percent'] = round(min(max(percent, 0), 100), 1)


def build_dashboard_stats(store):
    """Build a small summary payload for the dashboard view."""
    activities = store.get('activities', [])
    total_distance = get_yearly_total(store)
    total_by_type = {'run': 0.0}
    recent = []

    for item in activities:
        activity_type = normalize_activity_type(item.get('type'))
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
    update_goal_progress(store)

    return {
        'total_distance': round(total_distance, 2),
        'total_by_type': {key: round(value, 2) for key, value in total_by_type.items()},
        'workout_count': workout_count,
        'recent': recent,
        'year_to_date_miles': store.get('year_to_date_miles'),
        'effective_yearly_total': get_yearly_total(store),
    }


def build_funny_stats(store):
    """Generate three random fun facts."""

    yearly = get_yearly_total(store)

    stats = [
        {
            "title": "🦒 Giraffes",
            "value": f"You've run the length of {yearly * 5280 / 18:,.0f} giraffes.",
            "detail": "An average giraffe is about 18 feet tall."
        },

        {
            "title": "🗽 Statue of Libraries",
            "value": f"You've climbed {yearly * 5280 / 305:,.0f} Statue of Liberty heights.",
            "detail": "The Statue of Liberty is 305 feet tall."
        },

        {
            "title": "🧱 LEGO Bricks",
            "value": f"You've covered {yearly * 1609344 / 31.8:,.0f} LEGO bricks.",
            "detail": "A LEGO brick is about 31.8 mm long."
        },

        {
            "title": "🏊 Olympic Pools",
            "value": f"You've run the length of {yearly / 0.0311:,.0f} Olympic pools.",
            "detail": "One Olympic pool is 50 meters long."
        },

        {
            "title": "🚌 School Buses",
            "value": f"You've run the length of {yearly * 5280 / 45:,.0f} school buses this year.",
            "detail": "A school bus is about 45 feet long."
        },

        {
            "title": "🏅 Marathons",
            "value": f"You've run farther than {yearly / 26.2:.1f} marathons.",
            "detail": "26.2 miles each."
        },

        {
            "title": "🏈 Football Fields",
            "value": f"You've crossed {yearly / 0.0682:,.0f} football fields.",
            "detail": "Including the end zones."
        },

        {
            "title": "🌎 Around Earth",
            "value": f"You've traveled {100 * yearly / 6783.5:.2f}% around Earth.",
            "detail": "Earth's circumference is about 6,783.5 miles."
        },

        {
            "title": "🌙 Moon",
            "value": f"You're {100 * yearly / 238900:.3f}% of the way to the Moon.",
            "detail": "Keep running!"
        },

        {
            "title": "🐜 Ants",
            "value": f"Your miles equal about {yearly * 316800 / 1_000_000:.1f} million ants lined up.",
            "detail": "Assuming each ant is about one inch long."
        },

        {
            "title": "🏃 Track Laps",
            "value": f"You've run {yearly / 0.2485:,.0f} laps of a 400m track.",
            "detail": "That's a lot of circles."
        },

        {
            "title": "🚗 Across Texas",
            "value": f"You've crossed Texas {yearly / 801:.2f} times.",
            "detail": "Texas is about 801 miles wide."
        },
    ]

    random.shuffle(stats)

    return stats[:3]


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
            'year_to_date_miles': None,
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


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    """Show a dashboard with summaries, funny stats, and recent activity history."""
    store = get_user_store()

    if request.method == 'POST':
        raw_value = (request.form.get('year_to_date_miles') or '').strip()
        try:
            store['year_to_date_miles'] = float(raw_value) if raw_value else None
        except ValueError:
            flash('Please enter a valid number of miles.', 'danger')
            store['year_to_date_miles'] = None
        else:
            store['year_to_date_miles_baseline_seq'] = (store.get('next_activity_seq', 1) - 1) if store['year_to_date_miles'] is not None else None
            flash('Year-to-date miles updated.', 'success')
        return redirect(url_for('dashboard'))

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
            update_goal_progress(store)
            return redirect(url_for('activities'))

        if request.form.get('name'):
            try:
                distance = float(request.form.get('distance') or 0)
            except ValueError:
                distance = 0

            try:
                duration_minutes = float(request.form.get('duration_minutes') or 0)
            except ValueError:
                duration_minutes = 0

            user_activities.append({
                'name': request.form.get('name'),
                'type': 'Run',
                'start_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                'distance': round(distance, 2),
                'duration_seconds': int(duration_minutes * 60),
                'source': 'local',
                'seq': next_activity_seq(store),
            })
            flash('Activity added.', 'success')
            update_goal_progress(store)
            return redirect(url_for('activities'))

    # When the page loads, show Strava-connected activities and the recent activity list.
    strava_connected = 'strava_access_token' in session
    update_goal_progress(store)
    if not strava_connected and not user_activities:
        flash('Tip: connect Strava on the activities page to sync your training history.', 'info')
    if strava_connected:
        for item in fetch_strava_activities(session['strava_access_token']):
            if not is_run_activity(item):
                continue
            strava_id = item.get('id')
            if any(act.get('strava_id') == strava_id for act in user_activities if act.get('strava_id') is not None):
                continue
            raw_start = item.get('start_date_local', '')
            duration_seconds = item.get('moving_time', item.get('elapsed_time', 0)) or 0
            user_activities.append({
                'name': item.get('name') or 'Strava activity',
                'type': 'Run',
                'start_date': format_activity_start_date(raw_start),
                'distance': round(item.get('distance', 0) / 1609.34, 2),
                'duration_seconds': duration_seconds,
                'source': 'strava',
                'strava_id': strava_id,
                'pace_text': format_pace_minutes_per_mile(item.get('average_speed')),
                'seq': next_activity_seq(store),
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
          <h2>Log a run</h2>
          <form method="post" class="activity-form">
            <input type="hidden" name="action" value="add">
            <label>Name
              <input type="text" name="name" placeholder="Morning Run" required>
            </label>
            <label>Distance (mi)
              <input type="number" step="0.01" min="0" name="distance" placeholder="3.1">
            </label>
            <label>Duration (minutes)
              <input type="number" step="1" min="0" name="duration_minutes" placeholder="30">
            </label>
            <button type="submit">Add activity</button>
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

        if goal_type != 'run':
            flash('Only running goals are supported right now.', 'danger')
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
        update_goal_progress(store)
        flash('Goal created.', 'success')
        return redirect(url_for('view_goals'))

    update_goal_progress(store)
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
        if not is_run_activity(item):
            continue
        strava_id = item.get('id')
        if any(act.get('strava_id') == strava_id for act in user_activities if act.get('strava_id') is not None):
            continue

        user_activities.append({
            'name': item.get('name') or 'Strava activity',
            'type': 'Run',
            'start_date': item.get('start_date_local', '').replace('T', ' '),
            'distance': round(item.get('distance', 0) / 1609.34, 2),
            'source': 'strava',
            'strava_id': strava_id,
            'pace_text': format_pace_minutes_per_mile(item.get('average_speed')),
            'seq': next_activity_seq(store),
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