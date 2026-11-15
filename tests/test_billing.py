from datetime import datetime, timezone
from decimal import Decimal
import io
import json
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from tt_gpt.billing import BillingError, Costs, CostsClient, CostsMonitor


NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


def response(value):
    return io.BytesIO(json.dumps(value).encode())


def collect(monitor):
    deadline = time.monotonic() + 2
    while monitor.future is not None:
        monitor.poll()
        if time.monotonic() >= deadline:
            raise AssertionError('billing worker timed out')
        time.sleep(.002)


class CostsClientTests(unittest.TestCase):
    def test_costs_are_summed_with_decimal_and_month_start_is_utc(self):
        payload = {'data': [{'results': [{'amount': {'value': '0.1', 'currency': 'usd'}},
                                        {'amount': {'value': '0.2', 'currency': 'usd'}}]}],
                   'has_more': False}
        with patch('tt_gpt.billing.urlopen') as mocked:
            mocked.return_value.__enter__.return_value = response(payload)
            result = CostsClient('test-admin-key', now=lambda: NOW).fetch()
            request = mocked.call_args.args[0]
        parameters = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(parameters['start_time'], [str(int(NOW.replace(day=1, hour=0).timestamp()))])
        self.assertEqual(result.usd, Decimal('0.3'))
        self.assertEqual(result.month, '2026-11')
        self.assertEqual(result.scope, 'organization')
        self.assertEqual(request.headers['Authorization'], 'Bearer test-admin-key')

    def test_project_filter_and_pagination(self):
        payloads = [
            {'data': [{'results': [{'amount': {'value': 1, 'currency': 'usd'}}]}],
             'has_more': True, 'next_page': 'next'},
            {'data': [{'results': [{'amount': {'value': 2, 'currency': 'usd'}}]}],
             'has_more': False},
        ]
        requests = []
        def open_page(request, timeout):
            requests.append(request)
            return response(payloads.pop(0))
        with patch('tt_gpt.billing.urlopen', side_effect=open_page):
            result = CostsClient('test-admin-key', 'proj_example', now=lambda: NOW).fetch()
        self.assertEqual(result.usd, 3)
        self.assertEqual(result.scope, 'project')
        parameters = parse_qs(urlparse(requests[1].full_url).query)
        self.assertEqual(parameters['project_ids[]'], ['proj_example'])
        self.assertEqual(parameters['page'], ['next'])

    def test_empty_buckets_mean_zero_reported_spend(self):
        with patch('tt_gpt.billing.urlopen') as mocked:
            mocked.return_value.__enter__.return_value = response({'data': [{'results': []}]})
            result = CostsClient('test-admin-key', now=lambda: NOW).fetch()
        self.assertEqual(result.usd, 0)

    def test_http_error_does_not_expose_body_or_key(self):
        error = HTTPError('https://api.openai.com/v1/organization/costs', 403, 'forbidden', {},
                          io.BytesIO(b'sensitive billing details'))
        with patch('tt_gpt.billing.urlopen', side_effect=error):
            with self.assertRaises(BillingError) as raised:
                CostsClient('test-admin-key', now=lambda: NOW).fetch()
        self.assertEqual(str(raised.exception), 'http_403')

    def test_non_usd_amount_is_not_mislabeled_as_usd(self):
        payload = {'data': [{'results': [{'amount': {'value': 1, 'currency': 'eur'}}]}]}
        with patch('tt_gpt.billing.urlopen') as mocked:
            mocked.return_value.__enter__.return_value = response(payload)
            with self.assertRaisesRegex(BillingError, 'unsupported_currency'):
                CostsClient('test-admin-key', now=lambda: NOW).fetch()


class CostsMonitorTests(unittest.TestCase):
    def test_status_does_not_wait_for_billing_request(self):
        gate = threading.Event()
        class Client:
            def fetch(self):
                gate.wait(2)
                return Costs(Decimal('1.23'), '2026-11', NOW.isoformat())
        monitor = CostsMonitor(Client())
        try:
            self.assertIn('loading', monitor.status())
            gate.set()
            collect(monitor)
            text = monitor.status()
            self.assertIn('organization spend', text)
            self.assertIn('USD 1.230000', text)
            self.assertIn('balance: not provided', text)
        finally:
            gate.set()
            monitor.close()

    def test_successful_result_is_cached_for_five_minutes(self):
        now = [0]
        class Client:
            calls = 0
            def fetch(self):
                self.calls += 1
                return Costs(Decimal('1.23'), '2026-11', NOW.isoformat())
        client = Client()
        monitor = CostsMonitor(client, clock=lambda: now[0])
        try:
            collect(monitor)
            monitor.status()
            self.assertEqual(client.calls, 1)
            now[0] = 301
            monitor.status()
            collect(monitor)
            self.assertEqual(client.calls, 2)
            self.assertNotIn('test-admin-key', json.dumps(monitor.snapshot()))
        finally:
            monitor.close()

    def test_failure_preserves_last_report_with_stale_warning(self):
        now = [0]
        class Client:
            error = False
            def fetch(self):
                if self.error:
                    raise BillingError('http_403')
                return Costs(Decimal('1.23'), '2026-11', NOW.isoformat())
        client = Client()
        monitor = CostsMonitor(client, clock=lambda: now[0])
        try:
            collect(monitor)
            client.error = True
            now[0] = 301
            monitor.status()
            collect(monitor)
            self.assertIn('USD 1.230000', monitor.status())
            self.assertIn('last refresh failed: http_403', monitor.status())
        finally:
            monitor.close()


if __name__ == '__main__':
    unittest.main()
