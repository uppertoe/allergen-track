import os
import pytz
import csv
import fcntl  # For Unix-based systems
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect

# Set the working directory to the directory where this script is located
app_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(app_dir)

# Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
csrf = CSRFProtect(app)

# Configure timezone from .env
TIMEZONE = pytz.timezone(os.getenv('TIMEZONE', 'Australia/Melbourne'))

# Configure session to last 7 days
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Allergens list
allergens = ["Eggs", "Baked Egg", "Rice", "Oat", "Peanuts", "Almond", "Hazelnut", "Cashew", "Macadamia", "Pistachio", "Pine Nut", "Other Treenuts", "Sesame", "Seeds", "Shellfish", "Fish"]

# Path to the CSV file
CSV_FILE = os.path.join(app_dir, 'user_data.csv')

def ensure_csv_header():
    """Ensure the CSV file has the correct headers."""
    file_exists = os.path.exists(CSV_FILE)
    
    with open(CSV_FILE, mode='a+', newline='') as file:
        fcntl.flock(file, fcntl.LOCK_EX)  # Lock the file
        try:
            file.seek(0)  # Go to the start of the file
            first_line = file.readline().strip()
            
            if not file_exists or first_line != 'username,allergen,timestamp':
                file.seek(0)
                file.truncate()
                writer = csv.writer(file)
                writer.writerow(['username', 'allergen', 'timestamp'])
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)  # Unlock the file

def load_user_data(username):
    """Load the user's data from the CSV file."""
    ensure_csv_header()
    user_data = defaultdict(list)
    
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='r') as file:
            fcntl.flock(file, fcntl.LOCK_SH)  # Shared lock for reading
            try:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['username'].strip().lower() == username.lower():
                        timestamp = datetime.fromisoformat(row['timestamp']).astimezone(TIMEZONE)
                        user_data[row['allergen']].append(timestamp)
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)  # Unlock the file
    
    return user_data

def save_user_data(username, allergen, timestamp):
    """Save the user's data to the CSV file."""
    ensure_csv_header()
    with open(CSV_FILE, mode='a', newline='') as file:
        fcntl.flock(file, fcntl.LOCK_EX)  # Lock the file for writing
        try:
            writer = csv.writer(file)
            # Convert the timestamp to UTC before saving
            timestamp_utc = timestamp.astimezone(pytz.utc)
            writer.writerow([username, allergen, timestamp_utc.isoformat()])
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)  # Unlock the file

def get_existing_users():
    """Retrieve a list of existing users from the CSV file."""
    users = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='r') as file:
            fcntl.flock(file, fcntl.LOCK_SH)  # Shared lock for reading
            try:
                reader = csv.DictReader(file)
                for row in reader:
                    users.add(row['username'].strip().lower())
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)  # Unlock the file
    return sorted(users)

def remove_user_data(username, allergen, current_date):
    """Remove the user's data from the CSV file for the given date."""
    if not os.path.exists(CSV_FILE):
        return

    # Load all data into memory first
    rows_to_keep = []
    
    with open(CSV_FILE, mode='r') as file:
        fcntl.flock(file, fcntl.LOCK_SH)  # Shared lock for reading
        reader = csv.DictReader(file)
        for row in reader:
            row_timestamp = datetime.fromisoformat(row['timestamp']).astimezone(TIMEZONE).date()
            if not (row['username'].strip().lower() == username.lower() and 
                    row['allergen'] == allergen and 
                    row_timestamp == current_date):
                rows_to_keep.append(row)
        fcntl.flock(file, fcntl.LOCK_UN)  # Unlock the file
    
    # Now write only the remaining rows back to the file
    with open(CSV_FILE, mode='w', newline='') as file:
        fcntl.flock(file, fcntl.LOCK_EX)  # Lock the file for writing
        writer = csv.DictWriter(file, fieldnames=['username', 'allergen', 'timestamp'])
        writer.writeheader()
        writer.writerows(rows_to_keep)
        fcntl.flock(file, fcntl.LOCK_UN)  # Unlock the file



def get_selected_allergens(username, current_date):
    """Get a list of allergens selected by the user on the current date."""
    selected_allergens = []

    if not os.path.exists(CSV_FILE):
        return selected_allergens

    with open(CSV_FILE, mode='r') as file:
        fcntl.flock(file, fcntl.LOCK_SH)  # Shared lock for reading
        try:
            reader = csv.DictReader(file)
            for row in reader:
                # Convert the timestamp from UTC to the configured timezone
                row_timestamp = datetime.fromisoformat(row['timestamp']).replace(tzinfo=pytz.utc).astimezone(TIMEZONE)
                if row['username'].strip().lower() == username.lower() and row_timestamp.date() == current_date:
                    selected_allergens.append(row['allergen'])
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)  # Unlock the file

    return selected_allergens

def get_current_date():
    """Return the current date based on the configured timezone."""
    return datetime.now(TIMEZONE).date()

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'username' in session:
        return redirect(url_for('grid'))
    
    if request.method == 'POST':
        username = request.form.get('username').strip().lower()
        session['username'] = username
        session.permanent = True  # Make the session last for 7 days
        session['user_data'] = load_user_data(username)
        return redirect(url_for('grid'))

    existing_users = get_existing_users()

    return render_template('index.html', existing_users=existing_users)

@app.route('/tracker', methods=['GET', 'POST'])
def tracker():
    username = session.get('username')
    
    if not username:
        return redirect(url_for('index'))
    
    current_date = get_current_date()

    # Load allergens selected for the current day
    selected_allergens = get_selected_allergens(username, current_date)

    if request.method == 'POST':
        allergen = request.form.get('allergen')
        # Record the timestamp in the configured timezone and convert to UTC for storage
        timestamp = datetime.now(TIMEZONE).astimezone(pytz.utc)

        if allergen in selected_allergens:
            # If allergen is already selected, remove it
            remove_user_data(username, allergen, current_date)
            selected_allergens.remove(allergen)
            action = 'removed'
        else:
            # Add the allergen data for the current day
            save_user_data(username, allergen, timestamp)
            selected_allergens.append(allergen)
            action = 'added'

        # Check if the request is expecting a JSON response (typically from AJAX)
        if request.accept_mimetypes['application/json'] >= request.accept_mimetypes['text/html']:
            return jsonify({'status': 'success', 'action': action})

    return render_template('tracker.html', allergens=allergens, selected_allergens=selected_allergens)

@app.route('/grid')
def grid():
    username = session.get('username')
    
    if not username:
        return redirect(url_for('index'))

    user_data = load_user_data(username)

    # Calculate the start of the two-week period (rolling view with today at the bottom)
    today = datetime.now(TIMEZONE).date()
    start_of_two_weeks = today - timedelta(days=13)

    # Get all dates for the past two weeks (14 days) with today at the bottom
    week_dates = [start_of_two_weeks + timedelta(days=i) for i in range(14)][::1]

    # Create grid data to check if an allergen has a record for each day
    grid_data = defaultdict(lambda: defaultdict(bool))

    for allergen in allergens:
        for timestamp in user_data[allergen]:
            timestamp_date = timestamp.date()
            if timestamp_date in week_dates:
                grid_data[allergen][timestamp_date] = True

    return render_template('grid.html', allergens=allergens, grid_data=grid_data, week_dates=week_dates, today=today)

@app.route('/logout')
def logout():
    """Clear the session and redirect to the index page."""
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5005)
