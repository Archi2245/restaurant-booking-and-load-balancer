
# Create a new file: database.py

import mysql.connector
from config import DB_CONFIG
from datetime import datetime, timedelta

def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        print(f"Database connection error: {e}")
        return None

# Function to get restaurant categories
def get_restaurant_categories():
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM restaurant_categories")
    categories = cursor.fetchall()
    cursor.close()
    conn.close()
    return categories

# Function to get restaurant menu items
def get_restaurant_menu(restaurant_id):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM menu_items 
        WHERE restaurant_id = %s AND is_available = TRUE
        ORDER BY name
    """, (restaurant_id,))
    menu_items = cursor.fetchall()
    cursor.close()
    conn.close()
    return menu_items

# Function to find available time slots
def find_available_slots(restaurant_id, date_str, party_size):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    
    # Convert date string to date object
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        day_of_week = booking_date.weekday() + 1  # 1=Monday, 7=Sunday
    except ValueError:
        return []
    
    # Use stored procedure if available, otherwise use direct query
    try:
        cursor.callproc('FindAvailableTables', (restaurant_id, booking_date, party_size))
        for result in cursor.stored_results():
            available_slots = result.fetchall()
            cursor.close()
            conn.close()
            return available_slots
    except mysql.connector.Error:
        # Fallback to direct query if stored procedure doesn't exist
        cursor.execute("""
            SELECT ts.slot_id, ts.start_time, ts.end_time, ts.max_capacity 
            FROM time_slots ts
            WHERE ts.restaurant_id = %s
            AND ts.day_of_week = %s
            AND (
                SELECT COUNT(*) FROM reservations r
                WHERE r.slot_id = ts.slot_id
                AND r.reservation_date = %s
            ) + %s <= ts.max_capacity
        """, (restaurant_id, day_of_week, booking_date, party_size))
        
        available_slots = cursor.fetchall()
        cursor.close()
        conn.close()
        return available_slots

# Function to add a restaurant review
def add_review(user_id, restaurant_id, rating, review_text):
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO reviews (user_id, restaurant_id, rating, review_text)
            VALUES (%s, %s, %s, %s)
        """, (user_id, restaurant_id, rating, review_text))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except mysql.connector.Error as e:
        print(f"Error adding review: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False

# Function to get restaurant reviews
def get_restaurant_reviews(restaurant_id):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.review_id, r.rating, r.review_text, r.review_date,
               u.name as user_name
        FROM reviews r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.restaurant_id = %s
        ORDER BY r.review_date DESC
    """, (restaurant_id,))
    
    reviews = cursor.fetchall()
    cursor.close()
    conn.close()
    return reviews

# Function to get advanced restaurant suggestions (load balancing)
def suggest_restaurants(city=None, category_id=None, max_results=5):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    
    # Try using stored procedure
    try:
        cursor.callproc('SuggestRestaurants', (city, max_results, category_id))
        for result in cursor.stored_results():
            restaurants = result.fetchall()
            cursor.close()
            conn.close()
            return restaurants
    except mysql.connector.Error:
        # Fallback to direct query
        query = """
            SELECT 
                r.restaurant_id, 
                r.name, 
                r.location,
                r.current_occupancy,
                r.seating_capacity,
                (r.current_occupancy / r.seating_capacity) AS occupancy_rate,
                COALESCE(
                    (SELECT AVG(rating) FROM reviews 
                     WHERE restaurant_id = r.restaurant_id), 
                    0
                ) AS avg_rating
            FROM restaurants r
            WHERE 1=1
        """
        params = []
        
        if city:
            query += " AND r.location LIKE %s"
            params.append(f"%{city}%")
        
        if category_id:
            query += " AND r.category_id = %s"
            params.append(category_id)
        
        query += """
            ORDER BY 
                occupancy_rate ASC,
                avg_rating DESC
            LIMIT %s
        """
        params.append(max_results)
        
        cursor.execute(query, tuple(params))
        restaurants = cursor.fetchall()
        cursor.close()
        conn.close()
        return restaurants

# Function to update busy hours prediction
def update_busy_hours_prediction(restaurant_id):
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    # Calculate busyness based on reservation history
    for day in range(7):  # 0=Sunday to 6=Saturday
        for hour in range(10, 23):  # Typical restaurant hours 10AM to 10PM
            # Count reservations for this day and hour over the past 4 weeks
            four_weeks_ago = datetime.now() - timedelta(days=28)
            
            cursor.execute("""
                SELECT COUNT(*) / 4 AS avg_bookings
                FROM reservations r
                JOIN time_slots ts ON r.slot_id = ts.slot_id
                WHERE r.restaurant_id = %s
                AND DAYOFWEEK(r.reservation_date) = %s  # 1=Sunday, 7=Saturday
                AND HOUR(ts.start_time) <= %s AND HOUR(ts.end_time) > %s
                AND r.reservation_date >= %s
            """, (restaurant_id, (day + 1) % 7 + 1, hour, hour, four_weeks_ago))
            
            result = cursor.fetchone()
            avg_bookings = result[0] if result else 0
            
            # Calculate busyness score (normalize to 0-1)
            cursor.execute("""
                SELECT MAX(seating_capacity) FROM restaurants WHERE restaurant_id = %s
            """, (restaurant_id,))
            max_capacity = cursor.fetchone()[0] or 50  # Default to 50 if NULL
            
            busyness_score = min(1.0, avg_bookings / max_capacity)
            
            # Update or insert busy_hours record
            cursor.execute("""
                INSERT INTO busy_hours (restaurant_id, day_of_week, hour_of_day, busyness_score)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE busyness_score = %s
            """, (restaurant_id, day, hour, busyness_score, busyness_score))
    
    conn.commit()
    cursor.close()
    conn.close()
# Create a new file: database.py

import mysql.connector
from config import DB_CONFIG
from datetime import datetime, timedelta

def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        print(f"Database connection error: {e}")
        return None

# Function to get restaurant categories
def get_restaurant_categories():
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM restaurant_categories")
    categories = cursor.fetchall()
    cursor.close()
    conn.close()
    return categories

# Function to get restaurant menu items
def get_restaurant_menu(restaurant_id):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM menu_items 
        WHERE restaurant_id = %s AND is_available = TRUE
        ORDER BY name
    """, (restaurant_id,))
    menu_items = cursor.fetchall()
    cursor.close()
    conn.close()
    return menu_items

# Function to find available time slots
def find_available_slots(restaurant_id, date_str, party_size):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    
    # Convert date string to date object
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        day_of_week = booking_date.weekday() + 1  # 1=Monday, 7=Sunday
    except ValueError:
        return []
    
    # Use stored procedure if available, otherwise use direct query
    try:
        cursor.callproc('FindAvailableTables', (restaurant_id, booking_date, party_size))
        for result in cursor.stored_results():
            available_slots = result.fetchall()
            cursor.close()
            conn.close()
            return available_slots
    except mysql.connector.Error:
        # Fallback to direct query if stored procedure doesn't exist
        cursor.execute("""
            SELECT ts.slot_id, ts.start_time, ts.end_time, ts.max_capacity 
            FROM time_slots ts
            WHERE ts.restaurant_id = %s
            AND ts.day_of_week = %s
            AND (
                SELECT COUNT(*) FROM reservations r
                WHERE r.slot_id = ts.slot_id
                AND r.reservation_date = %s
            ) + %s <= ts.max_capacity
        """, (restaurant_id, day_of_week, booking_date, party_size))
        
        available_slots = cursor.fetchall()
        cursor.close()
        conn.close()
        return available_slots

# Function to add a restaurant review
def add_review(user_id, restaurant_id, rating, review_text):
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO reviews (user_id, restaurant_id, rating, review_text)
            VALUES (%s, %s, %s, %s)
        """, (user_id, restaurant_id, rating, review_text))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except mysql.connector.Error as e:
        print(f"Error adding review: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False

# Function to get restaurant reviews
def get_restaurant_reviews(restaurant_id):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.review_id, r.rating, r.review_text, r.review_date,
               u.name as user_name
        FROM reviews r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.restaurant_id = %s
        ORDER BY r.review_date DESC
    """, (restaurant_id,))
    
    reviews = cursor.fetchall()
    cursor.close()
    conn.close()
    return reviews

# Function to get advanced restaurant suggestions (load balancing)
def suggest_restaurants(city=None, category_id=None, max_results=5):
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    
    # Try using stored procedure
    try:
        cursor.callproc('SuggestRestaurants', (city, max_results, category_id))
        for result in cursor.stored_results():
            restaurants = result.fetchall()
            cursor.close()
            conn.close()
            return restaurants
    except mysql.connector.Error:
        # Fallback to direct query
        query = """
            SELECT 
                r.restaurant_id, 
                r.name, 
                r.location,
                r.current_occupancy,
                r.seating_capacity,
                (r.current_occupancy / r.seating_capacity) AS occupancy_rate,
                COALESCE(
                    (SELECT AVG(rating) FROM reviews 
                     WHERE restaurant_id = r.restaurant_id), 
                    0
                ) AS avg_rating
            FROM restaurants r
            WHERE 1=1
        """
        params = []
        
        if city:
            query += " AND r.location LIKE %s"
            params.append(f"%{city}%")
        
        if category_id:
            query += " AND r.category_id = %s"
            params.append(category_id)
        
        query += """
            ORDER BY 
                occupancy_rate ASC,
                avg_rating DESC
            LIMIT %s
        """
        params.append(max_results)
        
        cursor.execute(query, tuple(params))
        restaurants = cursor.fetchall()
        cursor.close()
        conn.close()
        return restaurants

# Function to update busy hours prediction
def update_busy_hours_prediction(restaurant_id):
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    # Calculate busyness based on reservation history
    for day in range(7):  # 0=Sunday to 6=Saturday
        for hour in range(10, 23):  # Typical restaurant hours 10AM to 10PM
            # Count reservations for this day and hour over the past 4 weeks
            four_weeks_ago = datetime.now() - timedelta(days=28)
            
            cursor.execute("""
                SELECT COUNT(*) / 4 AS avg_bookings
                FROM reservations r
                JOIN time_slots ts ON r.slot_id = ts.slot_id
                WHERE r.restaurant_id = %s
                AND DAYOFWEEK(r.reservation_date) = %s  # 1=Sunday, 7=Saturday
                AND HOUR(ts.start_time) <= %s AND HOUR(ts.end_time) > %s
                AND r.reservation_date >= %s
            """, (restaurant_id, (day + 1) % 7 + 1, hour, hour, four_weeks_ago))
            
            result = cursor.fetchone()
            avg_bookings = result[0] if result else 0
            
            # Calculate busyness score (normalize to 0-1)
            cursor.execute("""
                SELECT MAX(seating_capacity) FROM restaurants WHERE restaurant_id = %s
            """, (restaurant_id,))
            max_capacity = cursor.fetchone()[0] or 50  # Default to 50 if NULL
            
            busyness_score = min(1.0, avg_bookings / max_capacity)
            
            # Update or insert busy_hours record
            cursor.execute("""
                INSERT INTO busy_hours (restaurant_id, day_of_week, hour_of_day, busyness_score)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE busyness_score = %s
            """, (restaurant_id, day, hour, busyness_score, busyness_score))
    
    conn.commit()
    cursor.close()
    conn.close()

    return True