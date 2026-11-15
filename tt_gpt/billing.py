"""Optional read-only OpenAI Costs API access, kept off the TeamTalk event loop."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOG = logging.getLogger(__name__)


class BillingError(Exception):
    pass


@dataclass(frozen=True)
class Costs:
    usd: Decimal
    month: str
    fetched_at: str
    scope: str = 'organization'


class CostsClient:
    def __init__(self, admin_key, project_id='', now=None):
        self.admin_key = admin_key
        self.project_id = project_id
        self.now = now or (lambda: datetime.now(timezone.utc))

    def fetch(self):
        now = self.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        parameters = [('start_time', int(start.timestamp())), ('end_time', int(now.timestamp())),
                      ('bucket_width', '1d'), ('limit', 31)]
        if self.project_id:
            parameters.append(('project_ids[]', self.project_id))
        total = Decimal(0)
        cursors = set()
        for _ in range(32):
            request = Request('https://api.openai.com/v1/organization/costs?' + urlencode(parameters),
                headers={'Authorization': 'Bearer ' + self.admin_key, 'User-Agent': 'tt-gpt/1.1'})
            try:
                with urlopen(request, timeout=10) as response:
                    payload = json.load(response, parse_float=Decimal)
                for bucket in payload['data']:
                    for item in bucket.get('results', []):
                        amount = item['amount']
                        if amount.get('currency', '').lower() != 'usd':
                            raise BillingError('unsupported_currency')
                        value = Decimal(str(amount['value']))
                        if not value.is_finite():
                            raise BillingError('invalid_amount')
                        total += value
                if not payload.get('has_more'):
                    return Costs(total, start.strftime('%Y-%m'), now.isoformat(),
                                 'project' if self.project_id else 'organization')
                cursor = payload.get('next_page')
                if not isinstance(cursor, str) or not cursor or cursor in cursors:
                    raise BillingError('invalid_pagination')
                cursors.add(cursor)
                parameters = [(key, value) for key, value in parameters if key != 'page']
                parameters.append(('page', cursor))
            except HTTPError as error:
                status = error.code
                error.close()
                raise BillingError(f'http_{status}') from None
            except (URLError, TimeoutError, OSError):
                raise BillingError('network_error') from None
            except (ValueError, TypeError, KeyError, AttributeError, InvalidOperation):
                raise BillingError('invalid_response') from None
        raise BillingError('pagination_limit')


class CostsMonitor:
    """Refresh at startup and on status requests, with a five-minute cache."""
    def __init__(self, client, clock=time.monotonic):
        self.client, self.clock = client, clock
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='billing')
        self.future = None
        self.latest = None
        self.error = None
        self.next_refresh = 0
        self.closed = False
        self.refresh()

    def refresh(self):
        if not self.closed and self.future is None and self.clock() >= self.next_refresh:
            self.future = self.pool.submit(self.client.fetch)
            self.next_refresh = self.clock() + 300

    def poll(self):
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            try:
                self.latest = future.result()
                self.error = None
            except Exception as error:
                self.error = str(error) if isinstance(error, BillingError) else 'internal_error'
                LOG.error('billing_error category=%s', self.error)

    def status(self):
        self.poll()
        self.refresh()
        if self.latest is None:
            state = self.error or 'loading'
            return f'OpenAI reported costs: unavailable ({state})\nOpenAI credit balance: not provided by Costs API'
        data = self.latest
        warning = f'; last refresh failed: {self.error}' if self.error else ''
        return (
            f'OpenAI reported {data.scope} spend ({data.month} UTC): USD {data.usd:.6f}\n'
            f'Costs updated: {data.fetched_at}; reporting may lag{warning}\n'
            'OpenAI credit balance: not provided by Costs API'
        )

    def snapshot(self):
        if self.latest is None:
            return {'available': False, 'error': self.error}
        data = self.latest
        return {'available': True, 'usd': str(data.usd), 'month_utc': data.month,
                'scope': data.scope, 'fetched_at': data.fetched_at, 'error': self.error}

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.poll()
