-- ============================================================
-- Federated Learning System Database Schema
-- Database Name: fl_audit_db
-- ============================================================

CREATE DATABASE IF NOT EXISTS fl_audit_db;
USE fl_audit_db;

-- 1. Users Table (Admin & Hospital accounts)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(150) NOT NULL,
    role VARCHAR(50) DEFAULT 'HOSPITAL',      -- 'ADMIN' or 'HOSPITAL'
    status VARCHAR(50) DEFAULT 'PENDING',     -- 'PENDING', 'APPROVED', 'REJECTED'
    otp VARCHAR(10) NULL,
    otp_expiry DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Audit Ledger Table (Blockchain Hash Chain)
CREATE TABLE IF NOT EXISTS audit_ledger (
    block_index INT PRIMARY KEY,
    timestamp DOUBLE NOT NULL,
    client_id VARCHAR(100) NOT NULL,
    update_hash VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,              -- 'ACCEPTED', 'REJECTED_HUGE_GRADIENT', etc.
    previous_hash VARCHAR(255) NOT NULL,
    current_hash VARCHAR(255) NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Insert Admin Accounts
INSERT INTO users (username, password, email, role, status)
VALUES (
    'akshay',
    'scrypt:32768:8:1$ZZVjhDp1irLUwHiC$fbe6c5e0ce4bfa82ea670a6cbac5bd179922a6e29a4bd3ae9c657a9ed02ff88b40aef29e0ecc4212f67fad16d5e7efb0caaecd62e978bf5184ef9d5f61061ff3',
    'akshaysuresh968@gmail.com',
    'ADMIN',
    'APPROVED'
)
ON DUPLICATE KEY UPDATE 
    password = VALUES(password),
    email = VALUES(email),
    role = 'ADMIN',
    status = 'APPROVED';
