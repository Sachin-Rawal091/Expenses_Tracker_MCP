"""Setup script — applies the full schema to the connected PostgreSQL database."""

from database import get_connection

SCHEMA_SQL = """
-- 1. Users
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    api_key_hash TEXT,
    api_key_created_at TIMESTAMP,
    auth_provider VARCHAR(50) DEFAULT 'local',
    external_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Sessions (Persistent access tokens)
CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP,
    device_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 3. Categories
CREATE TABLE IF NOT EXISTS categories (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 4. Subcategories
CREATE TABLE IF NOT EXISTS subcategories (
    id BIGSERIAL PRIMARY KEY,
    category_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category_id, name),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 5. Expenses
CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    subcategory_id BIGINT,
    amount NUMERIC(12, 2) NOT NULL,
    note TEXT,
    expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (subcategory_id) REFERENCES subcategories(id)
);

-- 6. Trigger for data isolation
CREATE OR REPLACE FUNCTION validate_expense_ownership()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM categories WHERE id = NEW.category_id AND user_id = NEW.user_id
    ) THEN
        RAISE EXCEPTION 'category_id % does not belong to user_id %', NEW.category_id, NEW.user_id;
    END IF;
    IF NEW.subcategory_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM subcategories WHERE id = NEW.subcategory_id AND category_id = NEW.category_id
        ) THEN
            RAISE EXCEPTION 'subcategory_id % does not belong to category_id %', NEW.subcategory_id, NEW.category_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validate_expense ON expenses;
CREATE TRIGGER trg_validate_expense
BEFORE INSERT OR UPDATE ON expenses
FOR EACH ROW EXECUTE FUNCTION validate_expense_ownership();

-- 7. Seed defaults function
CREATE OR REPLACE FUNCTION seed_default_categories(p_user_id BIGINT)
RETURNS VOID AS $$
BEGIN
    WITH data AS (
        SELECT * FROM jsonb_each('{
            "Food & Dining": ["Groceries", "Restaurants", "Snacks", "Coffee", "Delivery"],
            "Transportation": ["Fuel", "Public Transit", "Taxi/Uber", "Parking", "Maintenance"],
            "Housing": ["Rent", "Utilities", "Internet", "Repairs", "Furniture"],
            "Entertainment": ["Movies", "Games", "Streaming", "Events", "Hobbies"],
            "Shopping": ["Clothing", "Electronics", "Books", "Gifts", "Personal Care"],
            "Health": ["Medicine", "Doctor", "Gym", "Insurance", "Wellness"],
            "Education": ["Courses", "Books", "Stationery", "Tuition", "Exams"],
            "Bills & Utilities": ["Electricity", "Water", "Gas", "Phone", "Subscriptions"],
            "Travel": ["Flights", "Hotels", "Food", "Activities", "Transport"],
            "Miscellaneous": ["Other", "Donations", "Fees", "Fines", "Cash"]
        }'::jsonb)
    ),
    inserted_categories AS (
        INSERT INTO categories (user_id, name)
        SELECT p_user_id, key FROM data
        ON CONFLICT (user_id, name) DO NOTHING
        RETURNING id, name
    )
    INSERT INTO subcategories (category_id, user_id, name)
    SELECT c.id, p_user_id, sub.value
    FROM data d
    JOIN categories c ON c.name = d.key AND c.user_id = p_user_id
    CROSS JOIN LATERAL jsonb_array_elements_text(d.value) AS sub(value)
    ON CONFLICT (category_id, name) DO NOTHING;
END;
$$ LANGUAGE plpgsql;
"""

import asyncio

async def main():
    conn = await get_connection()
    try:
        await conn.execute(SCHEMA_SQL)
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS api_key_hash TEXT")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS api_key_created_at TIMESTAMP")
        except Exception:
            pass
        print("✅ Schema updated with Persistent Sessions support!")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
