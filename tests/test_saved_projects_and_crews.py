import json
import os
import re
import unittest
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch

from planning import jobs
from services import cart, projects
from tests.test_pages import PageTestCase


RESULT = {
    "summary": "Small workshop plan", "notes": ["Allow time for paint to dry."],
    "materials": [{"material_name": "Plywood", "specification": "4 x 8 ft sheet",
                   "quantity": 2, "unit": "sheet", "notes": "Two sheets for the walls.", "product_id": None}],
    "crew": {"label": "AI-estimated crew", "days": [2, 3],
             "members": [{"role": "carpenter", "workers": 2, "days": [2, 3]}]},
}


class SavedProjectsAndCrewsTests(PageTestCase):
    def make_job(self, owner=1, complete=True):
        job = jobs.submit_job(owner, "workshop-" + str(owner),
                              {"description": "Workshop", "project_type": "custom"}, "fast")
        claimed = jobs.claim_job("test-worker")
        self.assertEqual(claimed["id"], job["id"])
        if complete:
            claimed["status"] = "complete"
            claimed["result"] = deepcopy(RESULT)
            for stage in claimed["stages"]:
                claimed["stages"][stage] = "done"
        else:
            claimed["status"] = "failed"
        jobs.save_job(claimed, "test-worker")
        return jobs.get_job(job["id"], owner)

    def test_dashboard_redirects_to_account_and_has_no_overview_tab(self):
        client = self.log_in("user")
        response = client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/dashboard/settings"))
        html = client.get(response.location).get_data(as_text=True)
        self.assertIn("<h1>Account</h1>", html)
        self.assertNotRegex(html, r">\s*Overview\s*</a>")

    def test_pro_label_has_plus_in_the_public_pages(self):
        client = self.log_in("user")
        with patch("routes.planner.pro_access_allowed", return_value=True):
            for path in ("/home", "/planner", "/subscription/about-pro"):
                html = client.get(path).get_data(as_text=True)
                self.assertIn("Pro Deep Quantum Ultra Max+", html)
                self.assertNotRegex(html, r"Pro Deep Quantum Ultra Max(?!\+)")

    def test_save_buttons_from_results_and_history_share_the_original_plan(self):
        client = self.log_in("user")
        job = self.make_job()
        with patch("planning.presentation.get_products_by_ids", return_value={}):
            html = client.get("/planner/jobs/" + job["id"]).get_data(as_text=True)
        self.assertIn("Save Project", html)
        self.assertGreater(html.index('id="save-project"'), html.index('class="plan-project-details"'))
        history = client.get("/planner/history").get_data(as_text=True)
        self.assertIn('/planner/jobs/' + job["id"] + '/save', history)
        self.assertEqual(client.post('/planner/jobs/' + job["id"] + '/save').status_code, 400)
        response = client.post('/planner/jobs/' + job["id"] + '/save',
                               data={"csrf_token": "page-csrf", "return_to": "history"})
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.location.endswith('/planner/history'))
        # A repeat save keeps the same record and does not copy the plan JSON.
        saved_id = projects.save_job_as_project(1, job, "Workshop")
        self.assertEqual(projects.save_job_as_project(1, job, "Workshop again"), saved_id)
        self.assertEqual(projects.count_projects(1), 1)
        with jobs.connection() as db:
            self.assertEqual(db.execute('SELECT plan FROM saved_projects').fetchone()['plan'], '{}')
        history = client.get('/planner/history').get_data(as_text=True)
        saved = client.get('/dashboard/projects').get_data(as_text=True)
        row_pattern = r'<a class="plan-row"[\s\S]*?</a>'
        self.assertEqual(re.findall(row_pattern, history), re.findall(row_pattern, saved))
        detail = client.get('/dashboard/projects/' + str(saved_id))
        self.assertTrue(detail.location.endswith('/planner/jobs/' + job['id']))
        self.assertEqual(projects.get_project_details(saved_id, 1)['plan']['result'], job['result'])
        with patch("planning.presentation.get_products_by_ids", return_value={}):
            html = client.get(detail.location).get_data(as_text=True)
        for text in ('Plywood', 'Two sheets for the walls.', 'AI-estimated crew', '$1,760', '$2,640'):
            self.assertIn(text, html)

    def test_unsaving_from_results_and_history_keeps_the_history_job(self):
        client = self.log_in("user")
        job = self.make_job()
        for source in ('plan', 'history', ''):
            saved_id = projects.save_job_as_project(1, job, None)
            response = client.post('/dashboard/projects/' + str(saved_id) + '/delete',
                                   data={'csrf_token': 'page-csrf', 'return_to': source})
            self.assertIn(response.status_code, (302, 303))
            self.assertEqual(projects.count_projects(1), 0)
            self.assertEqual(jobs.get_job(job['id'], 1)['result'], RESULT)

    def test_other_users_and_unfinished_jobs_cannot_be_saved_or_removed(self):
        client = self.log_in('user')
        other = self.make_job(owner=2)
        saved_id = projects.save_job_as_project(2, other, None)
        for path in ('/planner/jobs/' + other['id'], '/dashboard/projects/' + str(saved_id)):
            self.assertEqual(client.get(path).status_code, 404)
        self.assertEqual(client.post('/planner/jobs/' + other['id'] + '/save',
                                    data={'csrf_token': 'page-csrf'}).status_code, 404)
        self.assertEqual(client.post('/dashboard/projects/' + str(saved_id) + '/delete',
                                    data={'csrf_token': 'page-csrf'}).status_code, 404)
        with self.assertRaises(ValueError):
            projects.save_job_as_project(1, other, None)
        self.assertFalse(projects.delete_project(saved_id, 1))
        self.assertEqual(projects.get_project_list(1), [])
        unfinished = self.make_job(complete=False)
        client.post('/planner/jobs/' + unfinished['id'] + '/save', data={'csrf_token': 'page-csrf'})
        self.assertEqual(projects.count_projects(1), 0)

    def test_project_crew_changes_are_saved_without_changing_the_ai_result(self):
        client = self.log_in('user')
        job = self.make_job()
        saved_id = projects.save_job_as_project(1, job, None)
        selected = deepcopy(RESULT['crew'])
        selected['label'] = 'My crew'
        selected['members'][0]['workers'] = 3
        response = client.post('/dashboard/projects/' + str(saved_id) + '/crew',
                               data={'csrf_token': 'page-csrf', 'crew': json.dumps(selected)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(projects.get_project_details(saved_id, 1)['crew'], selected)
        self.assertEqual(jobs.get_job(job['id'], 1)['result'], RESULT)
        with patch('planning.presentation.get_products_by_ids', return_value={}):
            html = client.get('/planner/jobs/' + job['id']).get_data(as_text=True)
        self.assertIn('My crew', html)
        self.assertIn('$2,640', html)

    def test_add_crew_uses_server_rates_and_preserves_the_product_cart(self):
        client = self.log_in('user')
        crew = deepcopy(RESULT['crew'])
        crew['members'][0]['rate'] = 0
        data = {'csrf_token': 'page-csrf', 'crew': json.dumps(crew)}
        with patch('services.cart.database_cursor') as product_database:
            response = client.post('/cart/crews/add', data=data)
            self.assertEqual(response.status_code, 303)
            client.post('/cart/crews/add', data=data)
            product_database.assert_not_called()
        selected = cart.get_cart_crews(1)
        self.assertEqual(len(selected), 1)
        self.assertIn('$1,760', selected[0]['estimate']['cost'])
        self.assertIn('$2,640', selected[0]['estimate']['cost'])
        with patch('routes.shopping.get_cart', return_value=[]):
            html = client.get('/cart').get_data(as_text=True)
        self.assertIn('Crew estimates', html)
        self.assertNotIn('Your cart is empty', html)
        product = {'product_id': 10, 'name': 'Framing nails', 'unit': 'box', 'quantity': 2,
                   'unit_price_cents': 1995, 'total_cents': 3990, 'error': None}
        with patch('routes.shopping.get_cart', return_value=[product]):
            html = client.get('/cart').get_data(as_text=True)
        for text in ('Framing nails', '$39.90', 'Crew estimates', '$1,760', '$2,640', 'Remove crew'):
            self.assertIn(text, html)
        self.assertFalse(cart.remove_crew(2, selected[0]['id']))
        client.post('/cart/crews/' + str(selected[0]['id']) + '/remove', data={'csrf_token': 'page-csrf'})
        self.assertEqual(cart.get_cart_crews(1), [])
        with patch('routes.shopping.get_cart', return_value=[product]):
            self.assertIn('Framing nails', client.get('/cart').get_data(as_text=True))

    def test_crew_input_requires_login_csrf_and_valid_selections(self):
        data = {'crew': json.dumps(RESULT['crew']), 'csrf_token': 'page-csrf'}
        client = self.signed_out_client()
        self.assertTrue(client.post('/cart/crews/add', data=data).location.endswith('/login'))
        client = self.log_in('user')
        self.assertEqual(client.post('/cart/crews/add', data={'crew': data['crew']}).status_code, 400)
        for invalid in ('{}', 'not json', json.dumps({'label': 'Empty', 'days': [1, 1], 'members': []})):
            client.post('/cart/crews/add', data={**data, 'crew': invalid})
        self.assertEqual(cart.get_cart_crews(1), [])
        self.assertEqual(cart.get_cart_crews(2), [])
        html = client.get('/crews').get_data(as_text=True)
        self.assertIn('Add Crew to Cart', html)
        self.assertIn('action="/cart/crews/add"', html)


@unittest.skipUnless(os.getenv('RUN_CATALOG_DB_TESTS') == '1', 'Opt-in temporary-table MySQL test')
class ProductCartDatabaseTests(unittest.TestCase):
    def test_product_cart_add_update_remove_and_ownership(self):
        import mysql.connector
        from dotenv import load_dotenv
        from utils.database import database_settings
        load_dotenv('.env')
        db = mysql.connector.connect(**database_settings(), ssl_disabled=False, time_zone='+00:00')
        try:
            with db.cursor() as cursor:
                for table in ('Product', 'Cart_item'):
                    cursor.execute(f'CREATE TEMPORARY TABLE `test_cart_{table}` LIKE `{table}`')
                    cursor.execute(f'CREATE TEMPORARY TABLE `{table}` LIKE `test_cart_{table}`')
                cursor.execute("""INSERT INTO Product (id,name,subCategory,category,price,stockQty,unit)
                    VALUES (1,'Test sheets','Sheathing','lumber',19.95,10,'sheet')""")
            db.commit()

            @contextmanager
            def temporary_cursor():
                try:
                    with db.cursor(dictionary=True) as cursor:
                        yield cursor
                    db.commit()
                except Exception:
                    db.rollback()
                    raise

            with patch('services.cart.database_cursor', temporary_cursor):
                self.assertEqual(cart.add_item(1, 1, 2), 'Test sheets')
                cart.add_item(1, 1, 1)
                self.assertEqual(cart.get_cart(1)[0]['quantity'], 3)
                self.assertEqual(cart.get_cart(1)[0]['total_cents'], 5985)
                self.assertEqual(cart.get_cart(2), [])
                with self.assertRaises(ValueError):
                    cart.change_quantity(2, 1, 4)
                with self.assertRaises(ValueError):
                    cart.add_item(1, 1, 20)
                for invalid in ('1.5', 0, -1, True, 2147483648):
                    with self.assertRaises(ValueError):
                        cart.add_item(1, 1, invalid)
                self.assertEqual(cart.get_cart(1)[0]['quantity'], 3)
                cart.change_quantity(1, 1, 4)
                self.assertEqual(cart.get_cart(1)[0]['total_cents'], 7980)
                with db.cursor() as cursor:
                    cursor.execute('UPDATE Product SET price = 7.50, stockQty = 2 WHERE id = 1')
                db.commit()
                self.assertEqual(cart.get_cart(1)[0]['total_cents'], 3000)
                self.assertIn('Only 2', cart.get_cart(1)[0]['error'])
                with self.assertRaises(ValueError):
                    cart.change_quantity(1, 1, 3)
                self.assertFalse(cart.remove_item(2, 1))
                self.assertTrue(cart.remove_item(1, 1))
                self.assertEqual(cart.get_cart(1), [])
        finally:
            db.close()
