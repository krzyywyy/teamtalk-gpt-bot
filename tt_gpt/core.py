from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import logging
import time

from .api import APIError

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    user_id: int
    username: str
    channel_id: int
    private: bool
    text: str
    admin: bool = False
    generation: int = 0

    @property
    def key(self):
        # Keep each person's public context separate from their private context.
        return (self.generation, self.user_id, self.username,
                0 if self.private else self.channel_id)


@dataclass(frozen=True)
class Reply:
    message: Message
    text: str
    private: bool


class BotCore:
    def __init__(self, api, model, clock=time.monotonic):
        self.api, self.model, self.clock = api, model, clock
        self.started = clock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='openai')
        self.waiting = deque()
        self.active = {}
        self.history = {}
        self.rates = defaultdict(deque)
        self.command_rates = defaultdict(deque)
        self.global_rate = deque()
        self.notices = {}
        self.reply_queue = deque(maxlen=64)
        self.stats = {'received': 0, 'answers': 0, 'errors': 0,
                      'input_tokens': 0, 'output_tokens': 0, 'last_seconds': 0}
        self.last_error = 'none'
        self.connection = 'starting'
        self.generation = 0
        self.closed = False

    def status(self):
        s = self.stats
        return (
            f'Bot: {self.connection}\nModel: {self.model}\n'
            f'Uptime: {int(self.clock() - self.started)} s\n'
            f'Queue: {len(self.waiting)}, active: {len(self.active)}\n'
            f'Messages: {s["received"]}, answers: {s["answers"]}, errors: {s["errors"]}\n'
            f'API tokens: input {s["input_tokens"]}, output {s["output_tokens"]}\n'
            f'Last API duration: {s["last_seconds"]:.1f} s\n'
            f'Last error: {self.last_error}\nHistory: RAM only, 30 min idle timeout'
        )

    def receive(self, msg):
        if self.closed or msg.generation != self.generation:
            return
        text = msg.text.strip()
        if not text:
            return
        self.stats['received'] += 1
        self.prune()
        if text.startswith('/'):
            commands = self.command_rates[(msg.user_id, msg.username)]
            now = self.clock()
            while commands and commands[0] <= now - 60:
                commands.popleft()
            if len(commands) >= 10:
                return
            commands.append(now)
        if text.lower() == '/status':
            self.reply_queue.append(Reply(msg, self.status() if msg.admin else
                'Komenda /status jest dostępna tylko dla administratorów serwera.', True))
            return
        if text.lower() == '/help':
            self.reply_queue.append(Reply(msg,
                'Napisz do mnie prywatnie albo na kanale, na którym jestem. '
                'Odpowiadam przez API OpenAI. /reset usuwa kontekst tej rozmowy. '
                '/status jest dla administratorów. Wiadomości kanału są publiczne.', True))
            return
        if text.lower() == '/reset':
            # Invalidate in-flight results for this conversation by removing its history.
            self.history.pop(msg.key, None)
            self.waiting = deque(m for m in self.waiting if m.key != msg.key)
            for future, (original, _) in list(self.active.items()):
                if original.key == msg.key:
                    future.cancel()
                    self.active[future] = (original, None)
            self.reply_queue.append(Reply(msg, 'Kontekst tej rozmowy został usunięty.', True))
            return
        if text.startswith('/'):
            self.reply_queue.append(Reply(msg, 'Nieznana komenda. Dostępne: /help, /reset, /status.', True))
            return
        if len(text) > 8000:
            self.reply_queue.append(Reply(msg, 'Skróć wiadomość do 8000 znaków.', True))
            return
        now = self.clock()
        rate = self.rates[(msg.user_id, msg.username)]
        for entries in (rate, self.global_rate):
            while entries and entries[0] <= now - 60:
                entries.popleft()
        if len(rate) >= 10 or len(self.global_rate) >= 30 or len(self.waiting) + len(self.active) >= 24:
            if now - self.notices.get(msg.user_id, -100) > 10:
                self.reply_queue.append(Reply(msg, 'Mam teraz dużo wiadomości. Spróbuj za chwilę.', True))
                self.notices[msg.user_id] = now
            return
        rate.append(now)
        self.global_rate.append(now)
        self.waiting.append(msg)
        self.schedule()

    def prune(self):
        now = self.clock()
        busy = {m.key for m in self.waiting} | {m.key for m, _ in self.active.values()}
        for key, (updated, _) in list(self.history.items()):
            if now - updated > 1800 and key not in busy:
                del self.history[key]
        for rates in (self.rates, self.command_rates):
            for key, entries in list(rates.items()):
                if not entries or entries[-1] <= now - 60:
                    del rates[key]
        self.notices = {key: timestamp for key, timestamp in self.notices.items() if now - timestamp < 60}

    def schedule(self):
        if self.closed:
            return
        busy = {m.key for m, _ in self.active.values()}
        for msg in list(self.waiting):
            if len(self.active) >= 2:
                break
            if msg.key in busy:
                continue
            self.waiting.remove(msg)
            history = self.history.get(msg.key, (0, []))[1]
            messages = history + [{'role': 'user', 'content': msg.text}]
            future = self.pool.submit(self.api.answer, messages)
            self.active[future] = (msg, messages)
            busy.add(msg.key)

    def poll(self):
        for future, (msg, messages) in list(self.active.items()):
            if not future.done():
                continue
            del self.active[future]
            if msg.generation != self.generation or messages is None:
                continue
            try:
                answer = future.result()
                self.stats['answers'] += 1
                self.stats['input_tokens'] += answer.input_tokens
                self.stats['output_tokens'] += answer.output_tokens
                self.stats['last_seconds'] = answer.seconds
                messages.append({'role': 'assistant', 'content': answer.text})
                # Limit memory and request costs, preserving complete user/assistant turns.
                while len(messages) > 12 or sum(len(m['content']) for m in messages) > 24000:
                    if len(messages) <= 2:
                        break
                    messages = messages[2:]
                self.history[msg.key] = (self.clock(), messages)
                self.reply_queue.append(Reply(msg, answer.text, msg.private))
                LOG.info('api_answer user_id=%d private=%s seconds=%.2f input_tokens=%d output_tokens=%d',
                         msg.user_id, msg.private, answer.seconds, answer.input_tokens, answer.output_tokens)
            except Exception as error:
                category = error.category if isinstance(error, APIError) else 'internal_api_error'
                self.stats['errors'] += 1
                self.last_error = category
                LOG.error('api_error category=%s user_id=%d', category, msg.user_id)
                self.reply_queue.append(Reply(msg,
                    'Nie mogę teraz uzyskać odpowiedzi z OpenAI. Spróbuj później. '
                    'Administrator może sprawdzić /status.', msg.private))
        self.schedule()
        replies = list(self.reply_queue)
        self.reply_queue.clear()
        return replies

    def forget_user(self, user_id):
        self.waiting = deque(m for m in self.waiting if m.user_id != user_id)
        self.reply_queue = deque((r for r in self.reply_queue if r.message.user_id != user_id), maxlen=64)
        self.history = {k: v for k, v in self.history.items() if k[1] != user_id}
        for future, (msg, _) in list(self.active.items()):
            if msg.user_id == user_id:
                future.cancel()
                self.active[future] = (msg, None)

    def disconnected(self):
        self.generation += 1
        self.waiting.clear()
        self.reply_queue.clear()
        self.history.clear()
        for future, (msg, _) in list(self.active.items()):
            future.cancel()
            self.active[future] = (msg, None)

    def close(self):
        self.closed = True
        self.disconnected()
        self.pool.shutdown(wait=True, cancel_futures=True)
