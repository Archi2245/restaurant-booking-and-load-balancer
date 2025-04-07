# Import the new database functions
from database import (
    get_restaurant_categories, get_restaurant_menu, 
    find_available_slots, add_review, get_restaurant_reviews,
    suggest_restaurants, update_busy_hours_prediction
)

# Add a route for restaurant details
@app.route('/restaurant/<int:restaurant_id>')
def restaurant_details(restaurant_id):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('show_restaurants'))
    
    cursor = conn.cursor(dictionary=True)
    
    # Get restaurant details
    cursor.execute("""
        SELECT r.*, c.category_name,
        (SELECT AVG(rating) FROM reviews WHERE restaurant_id = r.restaurant_id) AS avg_rating
        FROM restaurants r
        LEFT JOIN restaurant_categories c ON r.category_id = c.category_id
        WHERE r.restaurant_id = %s
    """, (restaurant_id,))
    
    restaurant = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not restaurant:
        flash("Restaurant not found", "danger")
        return redirect(url_for('show_restaurants'))
    
    # Get menu items
    menu_items = get_restaurant_menu(restaurant_id)
    
    # Get reviews
    reviews = get_restaurant_reviews(restaurant_id)
    
    return render_template(
        'restaurant_details.html', 
        restaurant=restaurant, 
        menu_items=menu_items,
        reviews=reviews
    )

# Modify book_table route to use time slots
@app.route('/book/<int:restaurant_id>', methods=['GET', 'POST'])
def book_table(restaurant_id):
    if 'user_id' not in session:
        flash("You need to log in first.", "warning")
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        user_id = session['user_id']
        booking_date = request.form['booking_date']
        slot_id = request.form['slot_id']
        num_people = int(request.form['num_people'])
        special_requests = request.form.get('special_requests', '')
        
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('show_restaurants'))
            
        cursor = conn.cursor(dictionary=True)
        
        # Check if slot is still available
        cursor.execute("""
            SELECT ts.max_capacity, 
                   (SELECT COUNT(*) FROM reservations r 
                    WHERE r.slot_id = ts.slot_id 
                    AND r.reservation_date = %s) AS current_bookings
            FROM time_slots ts
            WHERE ts.slot_id = %s
        """, (booking_date, slot_id))
        
        slot = cursor.fetchone()
        
        if not slot or (slot['current_bookings'] + num_people) > slot['max_capacity']:
            flash("Sorry, this time slot is no longer available.", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for('book_table', restaurant_id=restaurant_id))
            
        # Insert reservation
        cursor.execute("""
            INSERT INTO reservations 
            (user_id, restaurant_id, slot_id, num_people, reservation_date, special_requests, status, reservation_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, restaurant_id, slot_id, num_people, booking_date, special_requests, 'Confirmed'))
        
        # Update restaurant occupancy
        cursor.execute("""
            UPDATE restaurants
            SET current_occupancy = current_occupancy + %s
            WHERE restaurant_id = %s
        """, (num_people, restaurant_id))
        
        conn.commit()
        
        # Update busy hours prediction
        update_busy_hours_prediction(restaurant_id)
        
        flash("Booking successful!", "success")
        cursor.close()
        conn.close()
        return redirect(url_for('show_restaurants'))
    
    # GET request - show booking form with available slots
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template(
        'booking.html', 
        restaurant_id=restaurant_id, 
        min_date=today
    )

# Add a route to get available time slots via AJAX
@app.route('/api/available-slots', methods=['GET'])
def available_slots():
    restaurant_id = request.args.get('restaurant_id', type=int)
    date = request.args.get('date')
    party_size = request.args.get('party_size', type=int, default=2)
    
    if not restaurant_id or not date or not party_size:
        return jsonify({"error": "Missing parameters"}), 400
    
    slots = find_available_slots(restaurant_id, date, party_size)
    return jsonify(slots)

# Add a route for submitting reviews
@app.route('/review/<int:restaurant_id>', methods=['GET', 'POST'])
def review_restaurant(restaurant_id):
    if 'user_id' not in session:
        flash("You need to log in first.", "warning")
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        rating = int(request.form['rating'])
        review_text = request.form['review_text']
        
        if rating < 1 or rating > 5:
            flash("Rating must be between 1 and 5", "danger")
            return redirect(url_for('review_restaurant', restaurant_id=restaurant_id))
        
        success = add_review(session['user_id'], restaurant_id, rating, review_text)
        
        if success:
            flash("Your review has been submitted.", "success")
            return redirect(url_for('restaurant_details', restaurant_id=restaurant_id))
        else:
            flash("There was an error submitting your review.", "danger")
    
    return render_template('review_form.html', restaurant_id=restaurant_id)

# Enhance suggested restaurant route with more load balancing features
@app.route('/suggested-restaurants')
def suggested_restaurants():
    city = request.args.get('city')
    category_id = request.args.get('category', type=int)
    
    restaurants = suggest_restaurants(city, category_id, max_results=5)
    categories = get_restaurant_categories()
    
    return render_template(
        'suggested_restaurants.html',
        restaurants=restaurants,
        categories=categories,
        selected_city=city,
        selected_category=category_id
    )

# Add advanced DBMS analysis route
@app.route('/advanced-stats')
def advanced_stats():
    if 'user_id' not in session:
        flash("You need to log in to view statistics.", "warning")
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    if not conn:
        return render_template("advanced_stats.html", stats={})
    
    cursor = conn.cursor(dictionary=True)
    stats = {}
    
    # Peak hours analysis
    cursor.execute("""
        SELECT 
            day_of_week,
            CASE day_of_week
                WHEN 0 THEN 'Sunday'
                WHEN 1 THEN 'Monday'
                WHEN 2 THEN 'Tuesday'
                WHEN 3 THEN 'Wednesday'
                WHEN 4 THEN 'Thursday'
                WHEN 5 THEN 'Friday'
                WHEN 6 THEN 'Saturday'
            END as day_name,
            hour_of_day,
            CONCAT(hour_of_day, ':00') as hour_display,
            AVG(busyness_score) as avg_busyness
        FROM busy_hours
        GROUP BY day_of_week, hour_of_day
        ORDER BY avg_busyness DESC
        LIMIT 10
    """)
    stats['peak_hours'] = cursor.fetchall()
    
    # Booking cancellation rate
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN status = 'Cancelled' THEN 1 END) as cancelled_count,
            COUNT(*) as total_count,
            (COUNT(CASE WHEN status = 'Cancelled' THEN 1 END) / COUNT(*)) * 100 as cancellation_rate
        FROM reservations
    """)
    stats['cancellation'] = cursor.fetchone()
    
    # Restaurant efficiency
    cursor.execute("""
        SELECT 
            r.restaurant_id,
            r.name,
            COUNT(res.reservation_id) as reservation_count,
            AVG(res.num_people) as avg_party_size,
            (COUNT(res.reservation_id) * AVG(res.num_people)) / r.seating_capacity as efficiency_score
        FROM restaurants r
        LEFT JOIN reservations res ON r.restaurant_id = res.restaurant_id
        GROUP BY r.restaurant_id
        ORDER BY efficiency_score DESC
        LIMIT 5
    """)
    stats['efficiency'] = cursor.fetchall()
    
    # User booking patterns
    cursor.execute("""
        SELECT 
            u.user_id,
            u.name as user_name,
            COUNT(r.reservation_id) as booking_count,
            AVG(r.num_people) as avg_party_size,
            COUNT(DISTINCT r.restaurant_id) as unique_restaurants
        FROM users u
        JOIN reservations r ON u.user_id = r.user_id
        GROUP BY u.user_id
        ORDER BY booking_count DESC
        LIMIT 10
    """)
    stats['user_patterns'] = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template("advanced_stats.html", stats=stats)
# Add to your app.py

# Admin routes
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session.get('is_admin') != True:
        flash("You need admin privileges to access this page.", "danger")
        return redirect(url_for('home'))
    
    return render_template('admin/dashboard.html')

# Database Maintenance
@app.route('/admin/db-maintenance', methods=['GET', 'POST'])
def db_maintenance():
    if 'user_id' not in session or session.get('is_admin') != True:
        flash("You need admin privileges to access this page.", "danger")
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return redirect(url_for('admin_dashboard'))
        
        cursor = conn.cursor()
        
        if action == 'optimize':
            tables = ['restaurants', 'reservations', 'users', 'reviews', 'menu_items']
            for table in tables:
                cursor.execute(f"OPTIMIZE TABLE {table}")
            flash("Database tables optimized", "success")
        
        elif action == 'backup':
            from backup_db import backup_database
            success, message = backup_database()
            if success:
                flash(f"Database backup created: {message}", "success")
            else:
                flash(f"Backup failed: {message}", "danger")
        
        elif action == 'cleanup':
            # Clean up old records and logs
            thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            cursor.execute("""
                DELETE FROM activity_log 
                WHERE created_at < %s
            """, (thirty_days_ago,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            flash(f"Cleaned up {deleted_count} old log records", "success")
        
        cursor.close()
        conn.close()
        
        return redirect(url_for('db_maintenance'))
    
    # Get database statistics
    conn = get_db_connection()
    stats = {}
    
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        # Get table sizes
        cursor.execute("""
            SELECT 
                table_name, 
                table_rows,
                ROUND(data_length/1024/1024, 2) as data_size_mb,
                ROUND(index_length/1024/1024, 2) as index_size_mb,
                ROUND((data_length + index_length)/1024/1024, 2) as total_size_mb
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY total_size_mb DESC
        """, (DB_CONFIG['database'],))
        
        stats['table_sizes'] = cursor.fetchall()
        
        # Get database total size
        cursor.execute("""
            SELECT 
                SUM(ROUND((data_length + index_length)/1024/1024, 2)) as total_db_size_mb
            FROM information_schema.tables
            WHERE table_schema = %s
        """, (DB_CONFIG['database'],))
        
        stats['db_size'] = cursor.fetchone()
        
        cursor.close()
        conn.close()
    
    return render_template('admin/db_maintenance.html', stats=stats)

# Admin view of all activity logs
@app.route('/admin/activity-logs')
def admin_activity_logs():
    if 'user_id' not in session or session.get('is_admin') != True:
        flash("You need admin privileges to access this page.", "danger")
        return redirect(url_for('home'))
    
    page = request.args.get('page', 1, type=int)
    logs_per_page = 20
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('admin_dashboard'))
    
    cursor = conn.cursor(dictionary=True)
    
    # Get total count
    cursor.execute("SELECT COUNT(*) as total FROM activity_log")
    total_logs = cursor.fetchone()['total']
    
    # Calculate pagination
    total_pages = (total_logs + logs_per_page - 1) // logs_per_page
    offset = (page - 1) * logs_per_page
    
    # Get logs with user details
    cursor.execute("""
        SELECT l.*, u.name as user_name
        FROM activity_log l
        LEFT JOIN users u ON l.user_id = u.user_id
        ORDER BY l.created_at DESC
        LIMIT %s OFFSET %s
    """, (logs_per_page, offset))
    
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template(
        'admin/activity_logs.html', 
        logs=logs,
        page=page,
        total_pages=total_pages
    )

# View for analyzing query performance
@app.route('/admin/query-performance')
def admin_query_performance():
    if 'user_id' not in session or session.get('is_admin') != True:
        flash("You need admin privileges to access this page.", "danger")
        return redirect(url_for('home'))
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('admin_dashboard'))
    
    cursor = conn.cursor(dictionary=True)
    
    # Try to get slow query log info if available
    try:
        cursor.execute("SHOW VARIABLES LIKE 'slow_query_log'")
        slow_log_status = cursor.fetchone()
        
        cursor.execute("SELECT * FROM mysql.slow_log ORDER BY start_time DESC LIMIT 10")
        slow_queries = cursor.fetchall()
    except mysql.connector.Error:
        slow_log_status = {"Value": "OFF"}
        slow_queries = []
    
    # Get process list (currently running queries)
    cursor.execute("SHOW FULL PROCESSLIST")
    process_list = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'admin/query_performance.html',
        slow_log_status=slow_log_status,
        slow_queries=slow_queries,
        process_list=process_list
    )

if __name__ == '__main__':
    app.run(debug=True) 