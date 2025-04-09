DROP DATABASE IF EXISTS restaurant_db;
CREATE DATABASE restaurant_db;
USE restaurant_db;

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(15),
    password_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE restaurants (
    restaurant_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    location VARCHAR(255),
    seating_capacity INT,
    current_occupancy INT DEFAULT 0,
    menu TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reservations (
    reservation_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    restaurant_id INT,
    num_people INT NOT NULL DEFAULT 1,
    reservation_time DATETIME,
    status ENUM('Pending', 'Confirmed', 'Cancelled') DEFAULT 'Pending',
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(restaurant_id)
);

CREATE TABLE orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    restaurant_id INT,
    order_details TEXT,
    total_amount DECIMAL(10,2),
    order_status ENUM('Pending', 'Completed', 'Cancelled') DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(restaurant_id)
);

-- Insert restaurant data with correct column names
INSERT INTO restaurants (name, location, seating_capacity, current_occupancy, menu)
VALUES 
('Spice Villa', 'MG Road, Pune', 50, 10, 'Biryani, Paneer, Roti'),
('The Curry House', 'Koregaon Park, Pune', 60, 5, 'Dal Makhani, Butter Naan'),
('Tandoori Nights', 'FC Road, Pune', 40, 8, 'Chicken Tikka, Garlic Naan'),
('Veggie Treat', 'Baner, Pune', 30, 2, 'Veg Thali, Lassi'),
('Flavours of South', 'Aundh, Pune', 35, 3, 'Dosa, Idli, Sambar'),
('Urban Bites', 'Viman Nagar, Pune', 45, 4, 'Burgers, Fries, Wraps'),
('Grill & Chill', 'Kalyani Nagar, Pune', 55, 6, 'Grilled Chicken, Mojito'),
('Maharaja Bhoj', 'Camp, Pune', 70, 15, 'Rajasthani Thali, Chhachh'),
('Pasta Point', 'Hinjewadi, Pune', 25, 5, 'Pasta, Pizza, Garlic Bread'),
('Saffron Spice', 'Hadapsar, Pune', 50, 7, 'Butter Chicken, Rice, Roti');

select * from users;
ALTER TABLE restaurants ADD COLUMN source VARCHAR(20) DEFAULT 'local';
ALTER TABLE reservations ADD COLUMN num_people INT NOT NULL DEFAULT 1;

-- Add these tables to your database schema

-- Table for restaurant categories
CREATE TABLE restaurant_categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL,
    description TEXT
);

-- Add category relation to restaurants
ALTER TABLE restaurants 
ADD COLUMN category_id INT,
ADD FOREIGN KEY (category_id) REFERENCES restaurant_categories(category_id);

-- Table for menu items
CREATE TABLE menu_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    is_vegetarian BOOLEAN DEFAULT FALSE,
    is_available BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(restaurant_id)
);

-- Table for reservation time slots
CREATE TABLE time_slots (
    slot_id INT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id INT NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    max_capacity INT NOT NULL,
    day_of_week INT NOT NULL, -- 0=Sunday, 1=Monday, etc.
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(restaurant_id)
);

-- Enhance reservations table with time slots
ALTER TABLE reservations
ADD COLUMN slot_id INT,
ADD COLUMN reservation_date DATE,
ADD COLUMN special_requests TEXT,
ADD FOREIGN KEY (slot_id) REFERENCES time_slots(slot_id);

-- Table for user reviews
CREATE TABLE reviews (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    restaurant_id INT NOT NULL,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT,
    review_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(restaurant_id)
);

-- Table for restaurant busy hours prediction
CREATE TABLE busy_hours (
    id INT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id INT NOT NULL,
    day_of_week INT NOT NULL, -- 0=Sunday, 1=Monday, etc.
    hour_of_day INT NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    busyness_score FLOAT NOT NULL, -- 0 to 1 representing how busy
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(restaurant_id),
    UNIQUE KEY (restaurant_id, day_of_week, hour_of_day)
);
-- Stored procedure to find available tables for a given time
DELIMITER //
CREATE PROCEDURE FindAvailableTables(
    IN p_restaurant_id INT,
    IN p_date DATE,
    IN p_time TIME,
    IN p_party_size INT
)
BEGIN
    -- Find matching time slot
    SELECT ts.slot_id, ts.max_capacity
    FROM time_slots ts
    WHERE ts.restaurant_id = p_restaurant_id
    AND ts.day_of_week = WEEKDAY(p_date) + 1
    AND p_time BETWEEN ts.start_time AND ts.end_time
    -- Check current capacity
    AND (
        SELECT COUNT(*) FROM reservations r
        WHERE r.slot_id = ts.slot_id
        AND r.reservation_date = p_date
    ) + p_party_size <= ts.max_capacity;
END //
DELIMITER ;

-- Function to calculate restaurant rating
DELIMITER //
CREATE FUNCTION GetRestaurantRating(p_restaurant_id INT) 
RETURNS DECIMAL(3,2)
DETERMINISTIC
BEGIN
    DECLARE avg_rating DECIMAL(3,2);
    
    SELECT COALESCE(AVG(rating), 0) INTO avg_rating
    FROM reviews
    WHERE restaurant_id = p_restaurant_id;
    
    RETURN avg_rating;
END //
DELIMITER ;

-- Stored procedure for load balancing (suggesting restaurants)
DELIMITER //
CREATE PROCEDURE SuggestRestaurants(
    IN p_city VARCHAR(100),
    IN p_max_results INT,
    IN p_category_id INT
)
BEGIN
    SELECT 
        r.restaurant_id, 
        r.name, 
        r.location,
        r.current_occupancy,
        r.seating_capacity,
        (r.current_occupancy / r.seating_capacity) AS occupancy_rate,
        GetRestaurantRating(r.restaurant_id) AS avg_rating
    FROM restaurants r
    WHERE 
        r.location LIKE CONCAT('%', p_city, '%')
        AND (p_category_id IS NULL OR r.category_id = p_category_id)
    ORDER BY 
        occupancy_rate ASC,
        avg_rating DESC
    LIMIT p_max_results;
END //
DELIMITER ;
-- Create a trigger for automatic load balancing
DELIMITER //
CREATE TRIGGER after_reservation_insert
AFTER INSERT ON reservations
FOR EACH ROW
BEGIN
    -- Update current_occupancy in the restaurants table
    UPDATE restaurants 
    SET current_occupancy = (
        SELECT SUM(num_people) 
        FROM reservations 
        WHERE restaurant_id = NEW.restaurant_id
        AND status = 'Confirmed'
        AND DATE(reservation_time) = CURDATE()
    )
    WHERE restaurant_id = NEW.restaurant_id;
    
    -- Log the reservation activity
    INSERT INTO activity_log (user_id, activity_type, entity_id, details, created_at)
    VALUES (NEW.user_id, 'reservation_created', NEW.reservation_id, 
            CONCAT('Restaurant ID: ', NEW.restaurant_id, ', People: ', NEW.num_people), 
            NOW());
end//
DELIMITER ;

-- Create a trigger for cancellation updating
DELIMITER //
CREATE TRIGGER after_reservation_update
AFTER UPDATE ON reservations
FOR EACH ROW
BEGIN
    IF OLD.status != 'Cancelled' AND NEW.status = 'Cancelled' THEN
        -- Update current_occupancy in the restaurants table
        UPDATE restaurants 
        SET current_occupancy = current_occupancy - NEW.num_people
        WHERE restaurant_id = NEW.restaurant_id;
        
        -- Log the cancellation
        INSERT INTO activity_log (user_id, activity_type, entity_id, details, created_at)
        VALUES (NEW.user_id, 'reservation_cancelled', NEW.reservation_id, 
                CONCAT('Restaurant ID: ', NEW.restaurant_id, ', People: ', NEW.num_people), 
                NOW());
    END IF;
END//
DELIMITER ;

-- Create a table and trigger for activity logging
CREATE TABLE activity_log (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    activity_type VARCHAR(50) NOT NULL,
    entity_id INT,
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- Add a function to calculate restaurant popularity score
DELIMITER //
CREATE FUNCTION CalculatePopularityScore(
    p_restaurant_id INT
) 
RETURNS DECIMAL(10,2)
DETERMINISTIC
BEGIN
    DECLARE num_reservations INT;
    DECLARE avg_rating DECIMAL(3,2);
    DECLARE num_reviews INT;
    DECLARE score DECIMAL(10,2);
    
    -- Get number of reservations
    SELECT COUNT(*) INTO num_reservations
    FROM reservations
    WHERE restaurant_id = p_restaurant_id
    AND reservation_time >= DATE_SUB(NOW(), INTERVAL 30 DAY);
    
    -- Get average rating
    SELECT AVG(rating), COUNT(*) INTO avg_rating, num_reviews
    FROM reviews
    WHERE restaurant_id = p_restaurant_id;
    
    -- If no reviews, use default 3.0 rating
    IF avg_rating IS NULL THEN
        SET avg_rating = 3.0;
        SET num_reviews = 0;
    END IF;
    
    -- Calculate score: 60% reservations, 40% ratings
    SET score = (num_reservations * 0.6) + ((avg_rating * num_reviews) * 0.4);
    
    RETURN score;
END //
DELIMITER ;
