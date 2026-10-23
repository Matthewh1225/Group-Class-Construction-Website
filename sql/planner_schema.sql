-- Empty planner tables. Run once against the existing application database.
CREATE TABLE IF NOT EXISTS planner_jobs (
    id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    owner INT NOT NULL,
    submission_key VARCHAR(100) NOT NULL,
    request_hash CHAR(64) CHARACTER SET ascii NOT NULL,
    tier VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created DOUBLE NOT NULL,
    updated DOUBLE NOT NULL,
    lease_until DOUBLE NOT NULL DEFAULT 0,
    worker VARCHAR(100),
    data LONGTEXT NOT NULL,
    UNIQUE KEY planner_submission (owner, submission_key),
    UNIQUE KEY planner_owner_job (owner, id),
    INDEX planner_queue (status, created),
    INDEX planner_owner_created (owner, created),
    CONSTRAINT planner_jobs_user_fk FOREIGN KEY (owner)
        REFERENCES `User` (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS saved_projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    owner INT NOT NULL,
    job_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    name VARCHAR(120) NOT NULL,
    plan LONGTEXT NOT NULL,
    crew TEXT,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    created DOUBLE NOT NULL,
    updated DOUBLE NOT NULL,
    UNIQUE KEY saved_project_job (owner, job_id),
    CONSTRAINT saved_projects_user_fk FOREIGN KEY (owner)
        REFERENCES `User` (id) ON DELETE CASCADE,
    -- The saved project must belong to the same user as its planning job.
    CONSTRAINT saved_projects_job_fk FOREIGN KEY (owner, job_id)
        REFERENCES planner_jobs (owner, id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS crew_cart (
    id INT AUTO_INCREMENT PRIMARY KEY,
    owner INT NOT NULL,
    crew TEXT NOT NULL,
    -- Index a hash because the complete crew JSON is too long for a unique key.
    crew_hash CHAR(64) CHARACTER SET ascii NOT NULL,
    UNIQUE KEY crew_selection (owner, crew_hash),
    CONSTRAINT crew_cart_user_fk FOREIGN KEY (owner)
        REFERENCES `User` (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
