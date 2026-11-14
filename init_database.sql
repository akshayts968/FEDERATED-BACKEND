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

-- 3. Insert Default Admin Account (password: admin_password)
-- werkzeug hash for 'admin_password'
INSERT IGNORE INTO users (username, password, email, role, status)
VALUES (
    'admin',
    'scrypt:32768:8:1$hGzQj1mR1nZ5g9eX$a3407ceeeecda7eeea7ba80bc2350415392cf9c19b0244ff53d39589a5ad304d603a1fc6c98ae032a188be7d7a4ea3c8f33d77eaecdb79860bdae0350711eb63',
    'admin@flconsortium.org',
    'ADMIN',
    'APPROVED'
);
