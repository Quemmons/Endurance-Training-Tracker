from flask import Flask, flash, redirect, render_template_string, request, url_for


import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-change-me'

# In-memory placeholder data. Replace this with a database later.
activity_items = []
goal_items = []


def page(title, body):
    return render_template_string('''
        <!doctype html>
        <html>
          <head><title>{{ title }}</title></head>
          <body>
            <h1>{{ title }}</h1>
            <nav>
              <a href="/">Home</a> |
              <a href="/dashboard">Dashboard</a> |
              <a href="/activities">Activities</a> |
              <a href="/goals">Goals</a> |
              <a href="/profile">Profile</a>
            </nav>
            <hr>
            {{ body | safe }}
          </body>
        </html>
    ''', title=title, body=body)


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
        # TODO: validate and save a new activity here.
        flash('Activity saving is not implemented yet.', 'info')
        return redirect(url_for('activities'))

    rows = ''.join(
        f'<li>{item}</li>' for item in activity_items
    ) or '<li>No activities yet.</li>'

    body = f'''
        <form method="post">
          <input name="name" placeholder="Activity name" />
          <button type="submit">Add placeholder activity</button>
        </form>
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
    body = '''
        <p>Profile placeholder.</p>
        <p>TODO: add account info, authentication, and optional Strava connection here.</p>
    '''
    return page('Profile', body)



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

