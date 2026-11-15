"""Responses API client; only the Python standard library is required."""
from dataclasses import dataclass
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


INSTRUCTIONS = (
    'You are Chat GPT, a helpful assistant chatting through TeamTalk text messages. '
    'Answer in the language used by the person, usually Polish. Be natural, clear and concise. '
    'Use plain text suitable for a screen reader; avoid tables and complex Markdown. '
    'Keep most replies under 250 words unless more detail is requested. '
    'You cannot hear audio, browse the web, access the server, or execute commands. '
    'Do not claim you have done those things. Never claim to know configuration secrets. '
    'Messages in a public channel are public; do not reveal or invent private conversations.'
)


class APIError(Exception):
    def __init__(self, category):
        self.category = category
        super().__init__(category)


@dataclass(frozen=True)
class Answer:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0


class OpenAIClient:
    def __init__(self, key, model):
        self.key = key
        self.model = model

    def answer(self, messages):
        started = time.monotonic()
        body = json.dumps({
            'model': self.model, 'instructions': INSTRUCTIONS, 'input': messages,
            'max_output_tokens': 1800, 'reasoning': {'effort': 'low'}, 'store': False,
        }).encode('utf-8')
        for attempt in range(3):
            request = Request('https://api.openai.com/v1/responses', data=body, headers={
                'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json',
                'User-Agent': 'tt-gpt/1.0',
            })
            try:
                with urlopen(request, timeout=35) as response:
                    payload = json.load(response)
                text = '\n'.join(
                    content.get('text', content.get('refusal', ''))
                    for item in payload.get('output', [])
                    if item.get('type') == 'message'
                    for content in item.get('content', [])
                    if content.get('type') in ('output_text', 'refusal')
                ).strip()
                if not text:
                    raise APIError('empty_response')
                usage = payload.get('usage') or {}
                return Answer(text[:7000], usage.get('input_tokens', 0),
                              usage.get('output_tokens', 0), time.monotonic() - started)
            except HTTPError as error:
                try:
                    code = json.loads(error.read(16384)).get('error', {}).get('code')
                except (ValueError, AttributeError):
                    code = None
                finally:
                    error.close()
                category = code if code in {
                    'insufficient_quota', 'model_not_found', 'invalid_api_key',
                    'rate_limit_exceeded', 'unsupported_parameter',
                } else f'http_{error.code}'
                if error.code in (429, 500, 502, 503, 504) and category != 'insufficient_quota' and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise APIError(category) from None
            except (URLError, TimeoutError, socket.timeout, OSError):
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise APIError('network_timeout') from None
            except (ValueError, KeyError, TypeError):
                raise APIError('invalid_response') from None
        raise APIError('retry_limit')
