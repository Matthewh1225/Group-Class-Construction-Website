The planner, saved projects, and crew selections use the same Aiven MySQL
database as accounts and products. Both Flask and the worker read the existing
`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` settings through
`utils/database.py`.

From the project root, create the three tables with:

```powershell
.\.venv\Scripts\python.exe -m sql.init_planner
```

This runs `sql/planner_schema.sql`. It creates `planner_jobs`, `saved_projects`,
and `crew_cart` if they are missing, without importing or seeding any rows.
It does not alter existing tables. For a new installation, run
`sql/erd_schema.sql` first, then this command.

For an existing installation created without planner foreign keys, run
`sql/add_planner_relations.sql` once against the application database. This
changes the three `owner` columns to `INT` and adds the same constraints as a
fresh installation. It imports no data and does not alter the original tables.

Restart the website and any existing workers after updating the code. Start a
worker in a separate terminal with:

```powershell
.\.venv\Scripts\python.exe -m planning.worker
```

Queue submissions, claims, answers, and cancellations share a MySQL named lock.
The lock is specific to the database and remains held until the transaction
commits or rolls back. Claims also lock the selected job with `FOR UPDATE`.
This prevents duplicate claims and keeps the existing two-worker limit.
The lock is released before AI processing starts. Progress saves check the
worker ID and running status, so cancelled or interrupted jobs reject late saves.

MySQL named locks require explicit release after commit; see the
[MySQL locking documentation](https://dev.mysql.com/doc/refman/8.0/en/locking-functions.html).

Saved projects keep their job link, name, completion flag, and optional crew.
The linked job stores the plan; saved projects do not copy its JSON.
A unique owner/job key prevents duplicate saves. Crew cart
entries store validated JSON and its SHA-256 hash; the owner/hash unique key
prevents duplicate selections without indexing a long JSON string.
Each `owner` references `User.id` with `ON DELETE CASCADE`. Saved projects also
reference the planning job's `(owner, id)` pair, ensuring that the saved project
and job belong to the same user. Deleting a job removes its saved project;
deleting a saved project leaves the job intact. Deleting a user automatically
removes their jobs, saved projects, and crew selections in the same transaction.
The application only deletes the user row; MySQL handles the related records.
Ownership filters remain in application queries to enforce access permissions.
See [MySQL foreign keys](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html).

For an existing installation with `saved_projects.plan`, compare each snapshot
with its linked job before upgrading. Preserve any snapshot-only information
before dropping the column. Verify that `saved_projects_job_fk` links
`(owner, job_id)` to `planner_jobs(owner, id)` with `ON DELETE CASCADE`.
Then run `sql/remove_saved_plan_snapshots.sql` once and restart the website and
workers with the updated code. New installations already omit this column.

After follow-up questions, the worker reuses the saved interpreter specification.
Planners receive the original project, interpreted details, and answers, with
explicit answers taking priority over earlier assumptions. A manual restart
creates a new job and runs the interpreter again, keeping the original answers.

The application no longer reads local SQLite files or uses
`PLANNER_JOB_DATABASE`. Existing local files are left untouched and are not
imported. No extra database dependency is needed beyond the existing
`mysql-connector-python` package.

Run the tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To include the MySQL integration tests:

```powershell
$env:RUN_MYSQL_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests require permission to create and drop a database. They create a
random `planner_test_...` database, insert synthetic fixtures only there, and
drop it afterward. They never insert test projects into the application's
database. Tests cover concurrent claims and submissions, worker progress,
questions, expiry, cancellation, restart, project and crew storage, ownership,
account-deletion rollback, and Flask pages. AI responses are mocked to avoid
external API calls; storage and locking use real MySQL connections.
