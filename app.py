import os
import pytz
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, date, timedelta
from collections import defaultdict
import csv
from dotenv import load_dotenv

# Set the working directory to the directory where this script is located
app_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(app_dir)

# Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configure timezone from .env
TIMEZONE = pytz.timezone(os.getenv('TIMEZONE', 'Australia/Melbourne'))

# Sample allergens list
allergens = ["Eggs", "Dairy", "Wheat", "Rice", "Soy", "Peanuts", "Tree-Nuts", "Seeds", "Shellfish", "Fish"]

# Path to the CSV file
CSV_FILE = os.path.join(app_dir, 'user_data.csv')

def ensure_csv_header():
    """Ensure the CSV file has the correct headers."""
    file_exists = os.path.exists(CSV_FILE)
    
    with open(CSV_FILE, mode='a+', newline='') as file:
        file.seek(0)  # Go to the start of the file
        first_line = file.readline().strip()
        
        if not file_exists or first_line != 'username,allergen,timestamp':
            file.seek(0)
            file.truncate()
            writer = csv.writer(file)
            writer.writerow(['username', 'allergen', 'timestamp'])

def load_user_data(username):
    """Load the user's data from the CSV file."""
    ensure_csv_header()
    user_data = defaultdict(list)
    
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['username'].strip().lower() == username.lower():
                    timestamp = datetime.fromisoformat(row['timestamp'])
                    user_data[row['allergen']].append(timestamp)
    
    return user_data

def save_user_data(username, allergen, timestamp):
    """Save the user's data to the CSV file."""
    ensure_csv_header()
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([username, allergen, timestamp.isoformat()])

def clear_selections_if_new_day():
    """Clear allergen selections if the day has changed, considering the configured timezone."""
    today = datetime.now(TIMEZONE).date().isoformat()
    last_recorded_date = session.get('last_recorded_date')

    if last_recorded_date != today:
        session['selected_allergens'] = []
        session['last_recorded_date'] = today

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form.get('username').strip().lower()
        session['username'] = username
        session['user_data'] = load_user_data(username)
        return redirect(url_for('grid'))

    return render_template('index.html')

@app.route('/tracker', methods=['GET', 'POST'])
def tracker():
    username = session.get('username')
    
    if not username:
        return redirect(url_for('index'))
    
    # Ensure user_data is initialized for all allergens
    if 'user_data' not in session:
        session['user_data'] = {allergen: [] for allergen in allergens}

    # Clear selections if the day has changed
    clear_selections_if_new_day()

    user_data = session['user_data']

    if request.method == 'POST':
        allergen = request.form.get('allergen')
        
        # Initialize the allergen list if it doesn't exist
        if allergen not in user_data:
            user_data[allergen] = []
        
        timestamp = datetime.now(pytz.utc).astimezone(TIMEZONE)
        user_data[allergen].append(timestamp)
        save_user_data(username, allergen, timestamp)
        session['user_data'] = user_data  # Update the session with the new data
        
        # Store the selected allergen in session to keep the button active
        if allergen not in session['selected_allergens']:
            session['selected_allergens'].append(allergen)

    return render_template('tracker.html', allergens=allergens)

@app.route('/grid')
def grid():
    username = session.get('username')
    
    if not username:
        return redirect(url_for('index'))

    user_data = load_user_data(username)

    # Calculate the start of the two-week period (starting from Monday two weeks ago)
    today = datetime.now(TIMEZONE).date()
    start_of_two_weeks = today - timedelta(days=today.weekday() + 7)

    # Get all dates for the past two weeks (14 days)
    week_dates = [start_of_two_weeks + timedelta(days=i) for i in range(14)]

    # Create grid data to check if an allergen has a record for each day
    grid_data = defaultdict(lambda: defaultdict(bool))

    for allergen in allergens:
        for timestamp in user_data[allergen]:
            timestamp_date = timestamp.date()
            if timestamp_date in week_dates:
                grid_data[allergen][timestamp_date] = True

    return render_template('grid.html', allergens=allergens, grid_data=grid_data, week_dates=week_dates)

@app.route('/logout')
def logout():
    """Clear the session and redirect to the index page."""
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
