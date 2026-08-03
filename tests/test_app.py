import importlib
import uuid

from app import calculate_pace_minutes_per_mile, format_pace_minutes_per_mile


def test_calculate_pace_from_strava_speed():
    assert calculate_pace_minutes_per_mile(2.2352) == 12.0
    assert format_pace_minutes_per_mile(2.2352) == '12:00/mi'


def test_home_page_uses_template_content():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()

    response = client.get('/')
    assert response.status_code == 200
    assert b'Track runs, rides, swims, and progress toward your goals.' in response.data


def test_registration_creates_user_and_logs_in():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()
    username = f'testuser_{uuid.uuid4().hex[:8]}'

    response = client.post('/register', data={'username': username, 'password': 'secret123'}, follow_redirects=True)

    assert response.status_code == 200
    assert b'Hello,' in response.data


def test_login_authenticates_registered_user():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()
    username = f'loginuser_{uuid.uuid4().hex[:8]}'

    client.post('/register', data={'username': username, 'password': 'secret123'})
    response = client.post('/login', data={'username': username, 'password': 'secret123'}, follow_redirects=True)

    assert response.status_code == 200
    assert b'Hello,' in response.data


def test_activities_page_renders_and_accepts_post():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()

    response = client.get('/activities')
    assert response.status_code == 200

    response = client.post('/activities', data={'name': 'Tempo run'})
    assert response.status_code == 302

    follow_up = client.get('/activities')
    assert b'Tempo run' in follow_up.data


def test_registered_users_do_not_share_activity_data():
    app_module = importlib.import_module('app')
    first_user = f'user_a_{uuid.uuid4().hex[:8]}'
    second_user = f'user_b_{uuid.uuid4().hex[:8]}'

    first_client = app_module.app.test_client()
    second_client = app_module.app.test_client()

    first_client.post('/register', data={'username': first_user, 'password': 'secret123'})
    second_client.post('/register', data={'username': second_user, 'password': 'secret123'})

    first_client.post('/activities', data={'name': 'Private tempo run'})
    first_response = first_client.get('/activities')
    second_response = second_client.get('/activities')

    assert b'Private tempo run' in first_response.data
    assert b'Private tempo run' not in second_response.data


def test_goal_creation_is_persisted_for_the_logged_in_user():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()
    username = f'goaluser_{uuid.uuid4().hex[:8]}'

    client.post('/register', data={'username': username, 'password': 'secret123'})
    response = client.post('/goals', data={
        'goal_type': 'run',
        'target_value': '20',
        'start_date': '2026-01-01',
        'end_date': '2026-02-01',
        'description': 'Run 20 miles',
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Run 20 miles' in response.data


def test_profile_shows_account_details():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()
    username = f'profileuser_{uuid.uuid4().hex[:8]}'

    client.post('/register', data={'username': username, 'password': 'secret123'})
    response = client.get('/profile')

    assert response.status_code == 200
    assert b'Username:' in response.data
    assert b'Member since:' in response.data


def test_dashboard_accepts_manual_year_to_date_miles():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()
    username = f'yearlyuser_{uuid.uuid4().hex[:8]}'

    client.post('/register', data={'username': username, 'password': 'secret123'})
    response = client.post('/dashboard', data={'year_to_date_miles': '320.5'}, follow_redirects=True)

    assert response.status_code == 200
    assert b'320.5' in response.data
    assert b'Year-to-date miles' in response.data
