# Milestones

#### Video Demo: <URL HERE> https://youtu.be/rStTdIYIXW0

#### Description:

Milestones is a web app I built for runners who want one place to see how their training is actually going instead of scrolling through a feed of individual runs. It pulls activity data from Strava, tracks progress toward goals I set myself, and turns total mileage into a few fun comparisons, like how many Olympic pools I've swum the length of, what percentage of the way to the Moon I've run, or how many times I've crossed Texas. It's built with Flask, Jinja2, Bootstrap, and deployed on Render.

## Why I built it this way

Strava is great at logging individual runs, but it doesn't answer the question I actually care about: "How is my year going compared to the goals I set for myself?" That's what I wanted Milestones to do. I built it around three main ideas: automatically pull in my Strava data, let me correct that data when Strava is missing older runs, and track everything against goals that I create instead of generic statistics.

## How the app is put together

There's no real database. User accounts, activities, and goals all live in plain Python dictionaries in memory (`users` and `user_data` in `app.py`). I did this to keep the project focused on Flask instead of spending a lot of time setting up a database. The downside is that everything resets whenever the server restarts. If I continue working on this project, switching to SQLite or PostgreSQL would be the first thing I'd do.

Every page uses `get_user_store()`, which checks who's logged in using the Flask session cookie and returns that user's own data. Almost every route calls this function first, and it's what keeps one user's activities and goals separate from everyone else's.

Passwords are stored as SHA-256 hashes instead of plain text. That means I never save the actual password someone types, only the hashed version, so the original password couldn't simply be read if the `users` dictionary were exposed.

One thing that's a little unusual is that the app renders pages in two different ways. The Dashboard, Goals, Profile, Login, and Register pages all use Jinja2 templates (`templates/*.html`) that extend a shared `base.html` layout. The Home and Activities pages are built as Python f-strings inside the `page()` helper in `app.py` and rendered with `render_template_string`. This wasn't something I planned from the beginning. It happened as the project grew, and instead of rewriting everything close to the deadline, I made sure both approaches use the same navigation, links, and styling so the user can't tell which rendering method is being used. If I started the project over, I'd definitely stick to just one approach.

## Strava integration

Strava uses OAuth, which lets users connect their account without ever giving my app their password. When someone visits `/strava/connect`, they're sent to Strava's authorization page. After they approve the connection, Strava redirects back to `/strava/callback` with a temporary code. My app exchanges that code, along with its client secret, for an access token that gets stored in the session and used for future API requests.

Whenever the user syncs their activities, either manually through `/strava/sync` or automatically when the Activities page loads, each activity's Strava ID is checked against the activities already stored. That way syncing multiple times never creates duplicate runs.

## The manual mileage baseline

This was probably the hardest part of the project to design. Strava only knows about runs that exist in Strava. If someone already ran 470 miles before connecting their account, those miles don't magically appear. To fix that, the Dashboard has a "Year-to-date miles" box where the user can enter their real yearly mileage. If they enter 500, then 500 becomes the new starting point instead of adding 500 to whatever Strava already reports.

The tricky part was deciding what should count after that baseline is saved. My first version recorded the exact timestamp when the baseline was created and only counted activities that happened after that time. During testing I found a bug where a run logged just a second later sometimes wouldn't count because locally created activities only store time down to the minute instead of the second.

To solve that, every activity gets a sequence number when it's created using the per-user counter in `next_activity_seq()`. When the baseline is saved, it stores the highest sequence number that exists at that moment instead of a timestamp. After that, the yearly mileage is calculated as the baseline plus the distance of every activity with a higher sequence number. This completely avoids timestamp precision problems and still works correctly even if older activities get deleted later because sequence numbers never change.

## Goals and fun facts

Goals are intentionally simple. Each goal has a target distance, a date range, and a description. Every goal tracks progress against the same yearly mileage instead of maintaining separate counters. The `update_goal_progress()` function recalculates each goal's progress and completion percentage, clamped between 0 and 100, on almost every page load.

Instead of putting the progress directly into a CSS `width` property, the percentage is passed to the template as a `data-progress` attribute. Then a few lines of JavaScript in `app.js` set the actual width after the page loads. I switched to this because embedding Jinja's `{{ }}` syntax directly inside a `style` attribute caused problems with code editors trying to lint the CSS.

The Milestones fun facts card takes the user's yearly mileage and converts it into a dozen different comparisons, including giraffes, Olympic pools, and the percentage of the distance to the Moon. The list gets shuffled every time the dashboard loads, and three random facts are displayed. That means simply refreshing the page shows a different set without needing any extra buttons or JavaScript.

## What I'd improve next

Even though passwords are hashed, the app doesn't have a password reset feature yet. The Strava client secret also has a fallback value hardcoded in `app.py`, which I know isn't good practice. It should only ever come from an environment variable. And, as mentioned earlier, replacing the in-memory dictionaries with a real database would be the biggest improvement because right now restarting the server erases all stored data.

## AI tool usage

I used Claude (Anthropic) to help debug and expand parts of this project. It helped me work through the sequence-number solution for the mileage baseline, improve the navigation between the two page-rendering systems, and review my Strava OAuth implementation. I made sure I understood each of those parts well enough to explain and maintain them myself, and I've noted the specific places where AI was used in the code comments.
