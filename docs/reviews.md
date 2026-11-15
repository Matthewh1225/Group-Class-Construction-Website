Customer reviews
===============

Before running this version against another MySQL database, apply
`sql/customer_review.sql` to the same database used by the application. The
migration creates `Customer_review` if it does not exist and preserves existing
records. No new Python or JavaScript dependencies are needed.

Visitors can browse `/reviews`. Active, signed-in accounts can submit a general
review or choose an active catalog product, with a title, written feedback, and
a required 1–5 star rating. Reviews are shared through MySQL. Product names are
saved with the review so feedback remains understandable if a product is removed.
Public author names use the first name and last initial.

Search, review type, star rating, sort order, product, and page are URL filters.
The summary reflects the selected review type and product; search and rating
filters narrow the review list. Product cards link directly to their reviews.
Posting uses the site's existing CSRF checks and account validation, plus a
limit of five submissions per minute and twenty per hour per IP address.

Run the regression checks with:

```text
python -m unittest discover -s tests -v
```
