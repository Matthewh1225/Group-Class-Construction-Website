-- Run once to upgrade the planner tables created without foreign keys.
-- Existing records must have valid users and matching job owners.
ALTER TABLE planner_jobs
    MODIFY owner INT NOT NULL,
    ADD UNIQUE KEY planner_owner_job (owner, id),
    ADD CONSTRAINT planner_jobs_user_fk FOREIGN KEY (owner)
        REFERENCES `User` (id) ON DELETE CASCADE;

ALTER TABLE saved_projects
    MODIFY owner INT NOT NULL,
    ADD CONSTRAINT saved_projects_user_fk FOREIGN KEY (owner)
        REFERENCES `User` (id) ON DELETE CASCADE,
    ADD CONSTRAINT saved_projects_job_fk FOREIGN KEY (owner, job_id)
        REFERENCES planner_jobs (owner, id) ON DELETE CASCADE;

ALTER TABLE crew_cart
    MODIFY owner INT NOT NULL,
    ADD CONSTRAINT crew_cart_user_fk FOREIGN KEY (owner)
        REFERENCES `User` (id) ON DELETE CASCADE;
