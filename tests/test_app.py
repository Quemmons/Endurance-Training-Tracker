import importlib


def test_activities_page_renders_and_accepts_post():
    app_module = importlib.import_module('app')
    client = app_module.app.test_client()

    response = client.get('/activities')
    assert response.status_code == 200

    response = client.post('/activities', data={'name': 'Tempo run'})
    assert response.status_code == 302

    follow_up = client.get('/activities')
    assert b'Tempo run' in follow_up.data
