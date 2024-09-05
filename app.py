import os
import pytz
import csv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy

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

# Set up SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Allergens list
allergens = ["Eggs", "Baked Egg", "Rice", "Oat", "Sesame", "Seeds", "Shellfish", "Fish", "Peanuts", "Almond", "Hazelnut", "Cashew", "Macadamia", "Pistachio", "Pine Nut", "Other Treenuts"]

CSV_FILE = os.path.join(app_dir, 'user_data.csv')

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)

class Allergen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class UserAllergen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    allergen_id = db.Column(db.Integer, db.ForeignKey('allergen.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    
    user = db.relationship('User', backref=db.backref('allergen_data', lazy=True))
    allergen = db.relationship('Allergen', backref=db.backref('user_data', lazy=True))

# Ensure the database is created
with app.app_context():
    db.create_all()

def load_data_from_csv():
    """Load data from the existing CSV into the SQLite database."""
    if not os.path.exists(CSV_FILE):
        print(f"CSV file '{CSV_FILE}' does not exist.")
        return

    # Read the CSV file and insert the data into the SQLite database
    with open(CSV_FILE, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            username = row['username'].strip().lower()
            allergen_name = row['allergen']
            timestamp = datetime.fromisoformat(row['timestamp']).replace(tzinfo=pytz.utc)

            # Get or create the user
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(username=username)
                db.session.add(user)
                db.session.commit()

            # Get or create the allergen
            allergen = Allergen.query.filter_by(name=allergen_name).first()
            if not allergen:
                allergen = Allergen(name=allergen_name)
                db.session.add(allergen)
                db.session.commit()

            # Save the record if it doesn't exist
            existing_record = UserAllergen.query.filter_by(user_id=user.id, allergen_id=allergen.id, timestamp=timestamp).first()
            if not existing_record:
                new_record = UserAllergen(user_id=user.id, allergen_id=allergen.id, timestamp=timestamp)
                db.session.add(new_record)
        db.session.commit()

    print("Data successfully loaded from CSV into the SQLite database.")

# Load data from CSV at app start
with app.app_context():
    load_data_from_csv()

# Helper functions
def load_user_data(username):
    """Load the user's data from the SQLite database."""
    user = User.query.filter_by(username=username.lower()).first()
    if not user:
        return defaultdict(list)
    
    user_data = defaultdict(list)
    records = UserAllergen.query.filter_by(user_id=user.id).all()
    
    for record in records:
        timestamp = record.timestamp.astimezone(TIMEZONE)
        user_data[record.allergen.name].append(timestamp)
    
    return user_data

def save_user_data(username, allergen_name, timestamp):
    """Save the user's data to the SQLite database."""
    # Get or create the user
    user = User.query.filter_by(username=username.lower()).first()
    if not user:
        user = User(username=username.lower())
        db.session.add(user)
        db.session.commit()

    # Get or create the allergen
    allergen = Allergen.query.filter_by(name=allergen_name).first()
    if not allergen:
        allergen = Allergen(name=allergen_name)
        db.session.add(allergen)
        db.session.commit()

    # Save the UserAllergen entry
    timestamp_utc = timestamp.astimezone(pytz.utc)
    new_record = UserAllergen(user_id=user.id, allergen_id=allergen.id, timestamp=timestamp_utc)
    db.session.add(new_record)
    db.session.commit()

def get_existing_users():
    """Retrieve a list of existing users from the SQLite database."""
    users = db.session.query(User.username).distinct().all()
    return sorted(set(user.username for user in users))

def remove_user_data(username, allergen_name, current_date):
    """Remove the user's data from the SQLite database for the given date."""
    user = User.query.filter_by(username=username.lower()).first()
    if not user:
        return

    allergen = Allergen.query.filter_by(name=allergen_name).first()
    if not allergen:
        return

    records_to_delete = UserAllergen.query.filter_by(user_id=user.id, allergen_id=allergen.id).all()
    for record in records_to_delete:
        if record.timestamp.astimezone(TIMEZONE).date() == current_date:
            db.session.delete(record)
    db.session.commit()

def get_selected_allergens(username, current_date):
    """Get a list of allergens selected by the user on the current date."""
    selected_allergens = []
    user = User.query.filter_by(username=username.lower()).first()
    if not user:
        return selected_allergens
    
    records = UserAllergen.query.filter_by(user_id=user.id).all()
    for record in records:
        record_date = record.timestamp.astimezone(TIMEZONE).date()
        if record_date == current_date:
            selected_allergens.append(record.allergen.name)
    return selected_allergens

def get_current_date():
    """Return the current date based on the configured timezone."""
    return datetime.now(TIMEZONE).date()

# Routes
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
