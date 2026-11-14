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
    'scrypt:32768:8:1$8WNyWCaH8dyWyviV$405ac9423fa097b6cf47b25c4a9210c438e78fb57c30e23a5d83c48a118ca17e5ad18aefe5648f30cce24ab2248b3d405dfec26b6599f121f20fc17edf980a51',
    'akshaysuresh968@gmail.com',
    'ADMIN',
    'APPROVED'
)
ON DUPLICATE KEY UPDATE 
    password = VALUES(password),
    email = VALUES(email),
    role = 'ADMIN',
    status = 'APPROVED';
