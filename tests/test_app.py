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
    assert b'Dashboard placeholder.' in response.data


def test_login_authenticates_registered_user():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()
    username = f'loginuser_{uuid.uuid4().hex[:8]}'

    client.post('/register', data={'username': username, 'password': 'secret123'})
    response = client.post('/login', data={'username': username, 'password': 'secret123'}, follow_redirects=True)

    assert response.status_code == 200
    assert b'Dashboard placeholder.' in response.data


def test_activities_page_renders_and_accepts_post():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()

    response = client.get('/activities')
    assert response.status_code == 200

    response = client.post('/activities', data={'name': 'Tempo run'})
    assert response.status_code == 302

    follow_up = client.get('/activities')
    assert b'Tempo run' in follow_up.data
