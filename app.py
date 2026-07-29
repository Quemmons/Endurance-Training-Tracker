from datetime import datetime
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Flask, flash, get_flashed_messages, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# In-memory placeholder data. Replace this with a database later.
# Each activity is stored as a dict, so we can show richer detail.
activity_items = []
goal_items = []

STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID', '260628')
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET', '87e49e77589f4ff35de2472bd4820b1af8fe347b')
STRAVA_REDIRECT_URI = os.environ.get('STRAVA_REDIRECT_URI', 'https://milestones-ktz9.onrender.com/strava/callback')
STRAVA_AUTH_URL = 'https://www.strava.com/oauth/authorize'
STRAVA_TOKEN_URL = 'https://www.strava.com/api/v3/oauth/token'
STRAVA_API_URL = 'https://www.strava.com/api/v3'


def is_strava_configured():
    return bool(STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET)


def build_strava_auth_url():
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


def upload_activity_to_strava(access_token, activity):
    payload = {
        'name': activity['name'],
        'type': activity['type'],
        'start_date_local': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'elapsed_time': int(activity.get('duration', 30) * 60),
        'distance': int(activity.get('distance', 5.0) * 1609.34),
        'description': activity.get('description', 'Uploaded from the endurance tracker shell'),
    }
    return requests.post(
        f'{STRAVA_API_URL}/activities',
        headers={'Authorization': f'Bearer {access_token}'},
        data=payload,
        timeout=30,
    )


def fetch_strava_activities(access_token):
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


def page(title, body):
    messages = ''.join(
        f'<div class="alert alert-{category}">{message}</div>'
        for category, message in get_flashed_messages(with_categories=True)
    )
    return render_template_string('''
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{{ title }}</title>
            <link rel="stylesheet" href="/static/css/styles.css">
          </head>
          <body class="app-body">
            <header class="site-header">
              <div class="container site-header-inner">
                <a class="site-logo" href="/">Endurance Tracker</a>
                <nav class="site-nav">
                  <a href="/">Home</a>
                  <a href="/dashboard">Dashboard</a>
                  <a href="/activities">Activities</a>
                  <a href="/goals">Goals</a>
                  <a href="/profile">Profile</a>
                </nav>
              </div>
            </header>
            <main class="page-content container">
              {{ messages | safe }}
              {{ body | safe }}
            </main>
          </body>
        </html>
    ''', title=title, body=body, messages=messages)


@app.route('/')
def home():
    body = '''
        <p>This is a stripped-down shell for your endurance tracker.</p>
        <p>Use this file to add the real pieces one by one.</p>
    '''
    return page('Home', body)


@app.route('/dashboard')
def dashboard():
    body = '''
        <p>Dashboard placeholder.</p>
        <p>TODO: calculate totals, weekly trends, and recent activity summaries here.</p>
    '''
    return page('Dashboard', body)


@app.route('/activities', methods=['GET', 'POST'])
def activities():
    if request.method == 'POST':
        name = request.form.get('name', '').strip() or 'Workout'
        upload_requested = request.form.get('upload_to_strava') == '1'

        activity_items.append({
            'name': name,
            'type': 'Run',
            'start_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
            'distance': 5.0,
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
            })

    def format_activity(a):
        distance = f"{a.get('distance', 0)} mi" if a.get('distance') is not None else 'unknown'
        return f"{a.get('name')} — {a.get('type')} — {a.get('start_date')} — {distance}"

    rows = ''.join(
        f'<li>{format_activity(item)}</li>' for item in activity_items
    ) or '<li>No activities yet.</li>'

    connect_link = '<a href="/strava/connect">Connect Strava</a>' if not strava_connected else '<a href="/strava/disconnect">Disconnect Strava</a>'
    sync_link = '<a href="/strava/sync">Sync from Strava</a>' if strava_connected else ''

    body = f'''
        <form method="post">
          <input name="name" placeholder="Activity name" />
          <label><input type="checkbox" name="upload_to_strava" value="1" /> Upload to Strava</label>
          <button type="submit">Save activity</button>
        </form>
        <p>{connect_link} {sync_link}</p>
        <ul>{rows}</ul>
        <p>TODO: wire this up to activity creation, editing, and deletion.</p>
    '''
    return page('Activities', body)


@app.route('/goals')
def goals():
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
    strava_status = 'Connected' if 'strava_access_token' in session else 'Not connected'
    body = f'''
        <p>Profile placeholder.</p>
        <p>Strava status: {strava_status}</p>
        <p>TODO: add account info, authentication, and optional Strava connection here.</p>
    '''
    return page('Profile', body)


@app.route('/strava/connect')
def strava_connect():
    if not is_strava_configured():
        flash('Strava integration is not configured yet. Add STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET.', 'warning')
        return redirect(url_for('profile'))

    return redirect(build_strava_auth_url())


@app.route('/strava/callback')
def strava_callback():
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
        })
        count += 1

    flash(f'Synced {count} activities from Strava.', 'success' if count else 'info')
    return redirect(url_for('activities'))


@app.route('/activity/delete/<activity_id>', methods=['POST'])
def delete_activity(activity_id):
    activity_items[:] = [item for item in activity_items if item.get('id') != activity_id]
    flash('Activity deleted.', 'info')
    return redirect(url_for('activities'))


@app.route('/strava/disconnect')
def strava_disconnect():
    session.pop('strava_access_token', None)
    session.pop('strava_refresh_token', None)
    session.pop('strava_athlete_id', None)
    session.pop('strava_oauth_state', None)
    flash('Strava disconnected.', 'info')
    return redirect(url_for('activities'))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

