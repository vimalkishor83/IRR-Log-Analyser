CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80) UNIQUE NOT NULL,
    password VARCHAR(120) NOT NULL,
    role VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_number VARCHAR(40) UNIQUE,
    application VARCHAR(120),
    server VARCHAR(120),
    environment VARCHAR(50),
    error_description TEXT,
    exception_message TEXT,
    root_cause TEXT,
    resolution TEXT,
    assignment_group VARCHAR(120),
    status VARCHAR(40),
    success_count INTEGER DEFAULT 1,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS kb_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200),
    error_pattern VARCHAR(300),
    root_cause TEXT,
    resolution TEXT,
    assignment_group VARCHAR(120),
    active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER,
    value VARCHAR(40),
    comments TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source VARCHAR(80),
    last_sync_time DATETIME,
    status VARCHAR(40),
    message TEXT
);

CREATE TABLE IF NOT EXISTS error_signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature VARCHAR(500) UNIQUE,
    application VARCHAR(120),
    server VARCHAR(120),
    severity VARCHAR(30),
    frequency INTEGER DEFAULT 1,
    last_seen DATETIME
);

CREATE TABLE IF NOT EXISTS knowledge_repository (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern VARCHAR(300),
    meaning TEXT,
    resolution TEXT,
    assignment_group VARCHAR(120),
    frequency INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT 1,
    last_seen DATETIME
);

CREATE TABLE IF NOT EXISTS parsed_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file VARCHAR(255),
    line_number INTEGER,
    timestamp DATETIME,
    severity VARCHAR(30),
    application VARCHAR(120),
    server VARCHAR(120),
    thread_id VARCHAR(80),
    error_code VARCHAR(80),
    exception VARCHAR(200),
    message TEXT,
    stack_trace TEXT,
    signature VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80),
    action VARCHAR(120),
    details TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT,
    result_count INTEGER,
    success BOOLEAN,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS recommendation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT,
    selected_source VARCHAR(80),
    confidence_score FLOAT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS application_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application VARCHAR(120) UNIQUE,
    health_score FLOAT,
    error_count INTEGER,
    critical_count INTEGER,
    incident_count INTEGER,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS learning_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name VARCHAR(120),
    metric_value FLOAT,
    updated_at DATETIME
);
