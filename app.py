
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import mysql.connector
from dotenv import load_dotenv
import os
from osm_api import search_restaurants
from auth import auth_bp  # Ensure 'auth.py' is inside a folder called 'auth' or root

# Load environment variables from .env
load_dotenv()

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret_key')  # Secure load

# Register Blueprint
app.register_blueprint(auth_bp)

# DB Connection
def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', 'archi@2245'),
            database=os.getenv('DB_NAME', 'restaurant_db')
        )
    except mysql.connector.Error as e:
        print(f"DB Connection Error: {e}")
        return None

# Save OSM restaurant to DB
def save_osm_restaurant_to_db(restaurant):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)

    # Check if already exists
    cursor.execute("""
        SELECT restaurant_id FROM restaurants 
        WHERE name = %s AND location = %s AND source = 'osm'
    """, (restaurant['name'], f"Lat: {restaurant['lat']}, Lon: {restaurant['lon']}"))
    
    existing = cursor.fetchone()
    if existing:
        cursor.close()
        conn.close()
        return existing['restaurant_id']
    
    # Insert new OSM restaurant
    cursor.execute("""
        INSERT INTO restaurants (name, location, seating_capacity, current_occupancy, menu, source)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        restaurant['name'],
        f"Lat: {restaurant['lat']}, Lon: {restaurant['lon']}",
        50, 0,
        "Menu not available", "osm"
    ))
    restaurant_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()
    return restaurant_id

# Home Route
@app.route('/')
def home():
    return render_template("index.html")

# Show restaurants route
@app.route('/restaurants')
def show_restaurants():
    conn = get_db_connection()
    if not conn:
        return render_template("restaurants.html", db_restaurants=[], osm_restaurants=[])

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM restaurants ORDER BY current_occupancy DESC LIMIT 20")

    db_restaurants = cursor.fetchall()

    city = request.args.get('city', 'Pune')
    osm_results = search_restaurants(city)[:10]
    
    osm_restaurants = []
    for r in osm_results:
        restaurant_id = save_osm_restaurant_to_db(r)
        if restaurant_id:
            r['restaurant_id'] = restaurant_id
            osm_restaurants.append(r)

    cursor.close()
    conn.close()
    return render_template("restaurants.html", db_restaurants=db_restaurants, osm_restaurants=osm_restaurants)

# Book table
@app.route('/book/<int:restaurant_id>', methods=['GET', 'POST'])
def book_table(restaurant_id):
    if 'user_id' not in session:
        flash("Login required", "warning")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        num_people = int(request.form['num_people'])
        user_id = session['user_id']
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('show_restaurants'))

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT seating_capacity, current_occupancy FROM restaurants WHERE restaurant_id = %s", (restaurant_id,))
        restaurant = cursor.fetchone()

        if not restaurant:
            flash("Restaurant not found", "danger")
        elif (restaurant['current_occupancy'] + num_people) <= restaurant['seating_capacity']:
            cursor.execute("""
                INSERT INTO reservations (user_id, restaurant_id, num_people, reservation_time, status)
                VALUES (%s, %s, %s, NOW(), 'Confirmed')
            """, (user_id, restaurant_id, num_people))
            cursor.execute("""
                UPDATE restaurants
                SET current_occupancy = current_occupancy + %s
                WHERE restaurant_id = %s
            """, (num_people, restaurant_id))
            conn.commit()
            flash("Reservation confirmed!", "success")
        else:
            flash("Not enough seats available.", "danger")

        cursor.close()
        conn.close()
        return redirect(url_for('show_restaurants'))

    return render_template('booking.html', restaurant_id=restaurant_id)

# Suggested least crowded restaurant
@app.route('/suggested-restaurant')
def suggested_restaurant():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB error"}), 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM restaurants ORDER BY current_occupancy ASC LIMIT 1")
    restaurant = cursor.fetchone()
    cursor.close()
    conn.close()

    if restaurant:
        return jsonify(restaurant)
    return jsonify({"error": "No restaurant found"}), 404

# Stats page
@app.route('/stats')
def restaurant_stats():
    if 'user_id' not in session:
        flash("Please login to view stats", "warning")
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    if not conn:
        return render_template("stats.html", stats={})

    cursor = conn.cursor(dictionary=True)
    stats = {}

    cursor.execute("""
        SELECT r.name, COUNT(*) as booking_count
        FROM reservations res
        JOIN restaurants r ON res.restaurant_id = r.restaurant_id
        GROUP BY res.restaurant_id
        ORDER BY booking_count DESC
        LIMIT 5
    """)
    stats['top_restaurants'] = cursor.fetchall()

    cursor.execute("""
        SELECT 
            AVG(current_occupancy) as avg_occupancy,
            MAX(current_occupancy) as max_occupancy,
            SUM(current_occupancy) as total_customers,
            AVG(current_occupancy / seating_capacity * 100) as avg_occupancy_percent
        FROM restaurants
    """)
    stats['occupancy'] = cursor.fetchone()

    cursor.execute("""
        SELECT 
            DAYNAME(reservation_time) as day_name,
            COUNT(*) as booking_count
        FROM reservations
        GROUP BY DAYNAME(reservation_time)
        ORDER BY FIELD(day_name, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
    """)
    stats['booking_by_day'] = cursor.fetchall()

    cursor.execute("""
        SELECT 
            COALESCE(source, 'local') as source, 
            COUNT(*) as restaurant_count,
            SUM(current_occupancy) as total_customers
        FROM restaurants
        GROUP BY source
    """)
    stats['source_stats'] = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("stats.html", stats=stats)

# 404 error handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route('/api/restaurant-occupancy')
def api_restaurant_occupancy():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT restaurant_id, current_occupancy FROM restaurants")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)


# Entry point
if __name__ == '__main__':
    app.run(debug=True)
=======
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import mysql.connector
from dotenv import load_dotenv
import os
from osm_api import search_restaurants
from auth import auth_bp  # Make sure auth.py is inside a folder called 'auth' or root

# Load environment variables from .env
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'archi12345'  # Replace with a secure secret key

# Register Blueprint
app.register_blueprint(auth_bp)

# DB Connection
def get_db_connection():
    try:
        db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', 'archi@2245'),
            'database': os.getenv('DB_NAME', 'restaurant_db')
        }
        return mysql.connector.connect(**db_config)
    except mysql.connector.Error as e:
        print(f"DB Connection Error: {e}")
        return None

# Save OSM restaurant to DB
def save_osm_restaurant_to_db(restaurant):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    
    # Check existence
    cursor.execute("""
        SELECT restaurant_id FROM restaurants 
        WHERE name = %s AND location = %s AND source = 'osm'
    """, (restaurant['name'], f"Lat: {restaurant['lat']}, Lon: {restaurant['lon']}"))
    
    existing = cursor.fetchone()
    if existing:
        cursor.close()
        conn.close()
        return existing['restaurant_id']
    
    # Insert if not exists
    cursor.execute("""
        INSERT INTO restaurants (name, location, seating_capacity, current_occupancy, menu, source)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        restaurant['name'],
        f"Lat: {restaurant['lat']}, Lon: {restaurant['lon']}",
        50, 0,
        "Menu not available", "osm"
    ))
    restaurant_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()
    return restaurant_id

# Home Route
@app.route('/')
def home():
    return render_template("index.html")

# Show restaurants route
@app.route('/restaurants')
def show_restaurants():
    conn = get_db_connection()
    if not conn:
        return render_template("restaurants.html", db_restaurants=[], osm_restaurants=[])
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM restaurants WHERE source = 'local' OR source IS NULL LIMIT 10")
    db_restaurants = cursor.fetchall()
    
    city = request.args.get('city', 'Pune')
    osm_results = search_restaurants(city)[:10]
    
    osm_restaurants = []
    for r in osm_results:
        restaurant_id = save_osm_restaurant_to_db(r)
        if restaurant_id:
            r['restaurant_id'] = restaurant_id
            osm_restaurants.append(r)
    
    cursor.close()
    conn.close()
    return render_template("restaurants.html", db_restaurants=db_restaurants, osm_restaurants=osm_restaurants)

# Book table
@app.route('/book/<int:restaurant_id>', methods=['GET', 'POST'])
def book_table(restaurant_id):
    if 'user_id' not in session:
        flash("Login required", "warning")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        num_people = int(request.form['num_people'])
        user_id = session['user_id']
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('show_restaurants'))
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT seating_capacity, current_occupancy FROM restaurants WHERE restaurant_id = %s", (restaurant_id,))
        restaurant = cursor.fetchone()

        if not restaurant:
            flash("Restaurant not found", "danger")
        elif (restaurant['current_occupancy'] + num_people) <= restaurant['seating_capacity']:
            cursor.execute("""
                INSERT INTO reservations (user_id, restaurant_id, num_people, reservation_time, status)
                VALUES (%s, %s, %s, NOW(), 'Confirmed')
            """, (user_id, restaurant_id, num_people))
            cursor.execute("""
                UPDATE restaurants
                SET current_occupancy = current_occupancy + %s
                WHERE restaurant_id = %s
            """, (num_people, restaurant_id))
            conn.commit()
            flash("Reservation confirmed!", "success")
        else:
            flash("Not enough seats available.", "danger")

        cursor.close()
        conn.close()
        return redirect(url_for('show_restaurants'))

    return render_template('booking.html', restaurant_id=restaurant_id)

# Suggest least crowded restaurant
@app.route('/suggested-restaurant')
def suggested_restaurant():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB error"}), 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM restaurants ORDER BY current_occupancy ASC LIMIT 1")
    restaurant = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if restaurant:
        return jsonify(restaurant)
    return jsonify({"error": "No restaurant found"}), 404

# Statistics and analytics
@app.route('/stats')
def restaurant_stats():
    if 'user_id' not in session:
        flash("Please login to view stats", "warning")
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    if not conn:
        return render_template("stats.html", stats={})
    
    cursor = conn.cursor(dictionary=True)
    stats = {}

    cursor.execute("""
        SELECT r.name, COUNT(*) as booking_count
        FROM reservations res
        JOIN restaurants r ON res.restaurant_id = r.restaurant_id
        GROUP BY res.restaurant_id
        ORDER BY booking_count DESC
        LIMIT 5
    """)
    stats['top_restaurants'] = cursor.fetchall()

    cursor.execute("""
        SELECT 
            AVG(current_occupancy) as avg_occupancy,
            MAX(current_occupancy) as max_occupancy,
            SUM(current_occupancy) as total_customers,
            AVG(current_occupancy / seating_capacity * 100) as avg_occupancy_percent
        FROM restaurants
    """)
    stats['occupancy'] = cursor.fetchone()

    cursor.execute("""
        SELECT 
            DAYNAME(reservation_time) as day_name,
            COUNT(*) as booking_count
        FROM reservations
        GROUP BY DAYNAME(reservation_time)
        ORDER BY FIELD(day_name, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
    """)
    stats['booking_by_day'] = cursor.fetchall()

    cursor.execute("""
        SELECT 
            COALESCE(source, 'local') as source, 
            COUNT(*) as restaurant_count,
            SUM(current_occupancy) as total_customers
        FROM restaurants
        GROUP BY source
    """)
    stats['source_stats'] = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("stats.html", stats=stats)

# Entry point
if __name__ == '__main__':
    app.run(debug=True)

