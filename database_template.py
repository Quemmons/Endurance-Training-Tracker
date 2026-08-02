import os
import sqlite3
from datetime import datetime

from flask import Flask, flash, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

DB_NAME = 'app.db'


def get_db():
    """Create a database connection for the current request."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the database tables if they do not already exist."""
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            distance REAL NOT NULL,
            duration TEXT NOT NULL,
            source TEXT NOT NULL,
            strava_id TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


init_db()


def add_activity(name, activity_type, distance, duration, source='local', strava_id=None):
    """Insert a new activity into the database."""
    conn = get_db()
    conn.execute(
        '''
        INSERT INTO activities (name, activity_type, start_date, distance, duration, source, strava_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            name,
            activity_type,
            datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
            round(float(distance), 2),
            duration,
            source,
            strava_id,
        ),
    )
    conn.commit()
    conn.close()


def get_activities():
    """Return all saved activities from the database."""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM activities ORDER BY id DESC'
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_activity(activity_id):
    """Delete an activity by ID."""
    conn = get_db()
    conn.execute('DELETE FROM activities WHERE id = ?', (activity_id,))
    conn.commit()
    conn.close()


def add_goal(title):
    """Insert a new goal into the database."""
    conn = get_db()
    conn.execute('INSERT INTO goals (title) VALUES (?)', (title,))
    conn.commit()
    conn.close()


def get_goals():
    """Return all saved goals from the database."""
    conn = get_db()
    rows = conn.execute('SELECT * FROM goals ORDER BY id DESC').fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.route('/')
def home():
    return render_template_string('''
        <h1>Milestones</h1>
        <p>Database template is ready.</p>
    ''')


@app.route('/activities', methods=['GET', 'POST'])
def activities():
    if request.method == 'POST':
        name = request.form.get('name', '').strip() or 'Workout'
        activity_type = request.form.get('type', 'Run').strip() or 'Run'
        distance = request.form.get('distance', '0').strip() or '0'
        duration = request.form.get('duration', '').strip() or '0'

        add_activity(name, activity_type, distance, duration)
        flash('Activity saved.', 'success')
        return redirect(url_for('activities'))

    activities_list = get_activities()
    return render_template_string('''
        <h2>Activities</h2>
        <form method="post">
            <input name="name" placeholder="Name" required>
            <input name="type" value="Run">
            <input name="distance" value="5" type="number" step="0.1">
            <input name="duration" value="30" type="number">
            <button type="submit">Save</button>
        </form>
        <ul>
            {% for item in activities_list %}
            <li>{{ item.name }} - {{ item.activity_type }} - {{ item.distance }} mi</li>
            {% endfor %}
        </ul>
    ''', activities_list=activities_list)


@app.route('/goals', methods=['GET', 'POST'])
def goals():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if title:
            add_goal(title)
            flash('Goal saved.', 'success')
        return redirect(url_for('goals'))

    goals_list = get_goals()
    return render_template_string('''
        <h2>Goals</h2>
        <form method="post">
            <input name="title" placeholder="Goal title" required>
            <button type="submit">Save</button>
        </form>
        <ul>
            {% for item in goals_list %}
            <li>{{ item.title }}</li>
            {% endfor %}
        </ul>
    ''', goals_list=goals_list)


if __name__ == '__main__':
    app.run(debug=True)
