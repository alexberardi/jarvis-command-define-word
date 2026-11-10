import re
from typing import Any, Optional
from urllib.parse import quote

import requests

from jarvis_command_sdk import (
    IJarvisCommand,
    CommandResponse,
    JarvisParameter,
    JarvisSecret,
    JarvisPackage,
    CommandExample,
    RequestInformation,
)

try:
    from jarvis_log_client import JarvisLogger
except ImportError:
    import logging

    class JarvisLogger:
        def __init__(self, **kw):
            self._log = logging.getLogger(kw.get('service', __name__))

        def info(self, msg, **kw):
            self._log.info(msg)

        def warning(self, msg, **kw):
            self._log.warning(msg)

        def error(self, msg, **kw):
            self._log.error(msg)

        def debug(self, msg, **kw):
            self._log.debug(msg)


logger = JarvisLogger(service='define_word')

API_URL = 'https://api.dictionaryapi.dev/api/v2/entries/en/'
WIKTIONARY_URL = 'https://en.wiktionary.org/w/api.php'
USER_AGENT = 'JarvisDefineWord/0.1 (community Jarvis package)'
REQUEST_TIMEOUT_SECONDS = 8
ETYMOLOGY_TIMEOUT_SECONDS = 5
MAX_DEFINITION_CHARS = 220
MAX_EXAMPLE_CHARS = 160
MAX_ETYMOLOGY_CHARS = 200
MAX_WORD_CHARS = 60
_DISALLOWED_CHARS = re.compile("[^A-Za-z' -]")
_HEADING = re.compile(r'^(={2,})\s*(.+?)\s*\1\s*$')
_PARENS = re.compile(r'\([^()]*\)')


class DefineWordCommand(IJarvisCommand):
    @property
    def command_name(self) -> str:
        return 'define_word'

    @property
    def description(self) -> str:
        return (
            'Look up the dictionary definition of an English word and give a short '
            'spoken definition with its part of speech, a short usage example and, '
            'when available, its etymology (word origin). Use for questions like '
            '"what does X mean", "define X" or "where does the word X come from".'
        )

    @property
    def parameters(self) -> list[JarvisParameter]:
        return [
            JarvisParameter(
                name='word',
                param_type='string',
                required=True,
                description='The single English word (or short phrase) to define, e.g. serendipity',
            ),
        ]

    @property
    def required_secrets(self) -> list[JarvisSecret]:
        return []

    @property
    def keywords(self) -> list[str]:
        return [
            'define',
            'definition',
            'meaning',
            'mean',
            'dictionary',
            'word',
            'what does',
            'look up',
            'etymology',
            'origin',
        ]

    @property
    def required_packages(self) -> list[JarvisPackage]:
        return [JarvisPackage('requests', '>=2.28.0')]

    @property
    def rules(self) -> list[str]:
        return [
            'Pass only the word being defined as the word parameter, without phrases like "what does" or "mean".',
        ]

    def generate_prompt_examples(self) -> list[CommandExample]:
        return [
            CommandExample(
                voice_command='What does serendipity mean?',
                expected_parameters={'word': 'serendipity'},
                is_primary=True,
            ),
            CommandExample(
                voice_command='Define ephemeral',
                expected_parameters={'word': 'ephemeral'},
            ),
            CommandExample(
                voice_command='What is the definition of ubiquitous?',
                expected_parameters={'word': 'ubiquitous'},
            ),
            CommandExample(
                voice_command='What is the etymology of scholastic?',
                expected_parameters={'word': 'scholastic'},
            ),
            CommandExample(
                voice_command='Look up the word pragmatic',
                expected_parameters={'word': 'pragmatic'},
            ),
        ]

    def generate_adapter_examples(self) -> list[CommandExample]:
        pairs = [
            ('What does serendipity mean?', 'serendipity'),
            ('Define ephemeral.', 'ephemeral'),
            ('What is the definition of ubiquitous?', 'ubiquitous'),
            ('Look up the word pragmatic', 'pragmatic'),
            ('What does the word ameliorate mean?', 'ameliorate'),
            ('Can you define benevolent for me?', 'benevolent'),
            ('Meaning of quixotic', 'quixotic'),
            ('Tell me what ennui means', 'ennui'),
            ('Define the word ambiguous', 'ambiguous'),
            ('What does lethargic mean?', 'lethargic'),
            ('Dictionary definition of paradigm', 'paradigm'),
            ('What does perfunctory mean', 'perfunctory'),
            ('How do you define resilience?', 'resilience'),
            ('Look up eloquent in the dictionary', 'eloquent'),
            ('What is the meaning of the word nostalgia?', 'nostalgia'),
            ('What is the etymology of scholastic?', 'scholastic'),
            ('Where does the word hello come from?', 'hello'),
        ]
        examples: list[CommandExample] = []
        for index, (voice, word) in enumerate(pairs):
            examples.append(
                CommandExample(
                    voice_command=voice,
                    expected_parameters={'word': word},
                    is_primary=(index == 0),
                )
            )
        return examples

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_word(raw: Any) -> str:
        if not isinstance(raw, str):
            return ''
        cleaned = _DISALLOWED_CHARS.sub('', raw)
        cleaned = ' '.join(cleaned.split()).lower()
        cleaned = cleaned.strip("-' ")
        return cleaned[:MAX_WORD_CHARS]

    @staticmethod
    def _shorten(text: str, limit: int = MAX_DEFINITION_CHARS) -> str:
        text = ' '.join(text.split()).strip()
        if len(text) <= limit:
            return text.rstrip('.;:, ')
        cut = text[:limit]
        # Prefer ending at a sentence or clause boundary
        for sep in ('. ', '; '):
            idx = cut.rfind(sep)
            if idx > 60:
                return cut[:idx].rstrip('.;:, ')
        idx = cut.rfind(' ')
        if idx > 0:
            cut = cut[:idx]
        return cut.rstrip('.;:, ') + '...'

    @staticmethod
    def _format_example(text: str) -> str:
        # Returns a spoken-friendly usage sentence, or '' when there is none
        text = ' '.join(str(text or '').split()).strip().strip('"\u201c\u201d')
        if not text:
            return ''
        if len(text) > MAX_EXAMPLE_CHARS:
            text = DefineWordCommand._shorten(text, MAX_EXAMPLE_CHARS)
        if text and text[-1] not in '.!?':
            text += '.'
        return text

    @staticmethod
    def _clean_etymology(raw: Any) -> str:
        # Make etymology text comfortable to speak: drop parenthetical notes and
        # words written in non-Latin scripts (which a TTS engine cannot read well).
        text = str(raw or '')
        for _ in range(5):
            stripped = _PARENS.sub('', text)
            if stripped == text:
                break
            text = stripped
        tokens = [
            token
            for token in text.split()
            if not any(ch.isalpha() and ord(ch) > 0x24F for ch in token)
        ]
        text = ' '.join(tokens)
        text = re.sub(r'\s+([,.;:])', r'\1', text)
        text = re.sub(r'([,;:])(\s*[,;:])+', r'\1', text)
        text = text.strip(' ,;:')
        if len(text) < 8:
            return ''
        return DefineWordCommand._shorten(text, MAX_ETYMOLOGY_CHARS)

    @staticmethod
    def _parse_wiktionary_etymology(extract: str) -> str:
        # Pulls the first English "Etymology" section out of a plain-text Wiktionary page
        in_english = False
        in_etymology = False
        buffer: list[str] = []
        for line in extract.splitlines():
            match = _HEADING.match(line.strip())
            if match:
                level = len(match.group(1))
                title = match.group(2).strip().lower()
                if level == 2:
                    if in_english:
                        break
                    in_english = (title == 'english')
                    in_etymology = False
                elif in_english:
                    if title.startswith('etymology'):
                        if buffer:
                            break
                        in_etymology = True
                    elif in_etymology:
                        break
                continue
            if in_etymology:
                stripped = line.strip()
                if stripped:
                    buffer.append(stripped)
        return ' '.join(buffer)

    @staticmethod
    def _fetch_etymology(word: str) -> str:
        # Best-effort fallback: never raises, returns '' when nothing usable is found
        try:
            response = requests.get(
                WIKTIONARY_URL,
                params={
                    'action': 'query',
                    'prop': 'extracts',
                    'explaintext': 1,
                    'redirects': 1,
                    'titles': word,
                    'format': 'json',
                    'formatversion': 1,
                },
                headers={'User-Agent': USER_AGENT},
                timeout=ETYMOLOGY_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                return ''
            data = response.json()
            pages = ((data or {}).get('query') or {}).get('pages') or {}
            for page in pages.values():
                if not isinstance(page, dict):
                    continue
                raw = DefineWordCommand._parse_wiktionary_etymology(str(page.get('extract') or ''))
                cleaned = DefineWordCommand._clean_etymology(raw)
                if cleaned:
                    return cleaned
            return ''
        except Exception as exc:
            logger.debug(f'Etymology lookup skipped: {exc}')
            return ''

    @staticmethod
    def _lower_first(text: str) -> str:
        # Lowercase the first letter after "meaning:" unless it looks like an acronym/proper noun
        if len(text) > 1 and text[0].isupper() and text[1].islower():
            return text[0].lower() + text[1:]
        return text

    @staticmethod
    def _article(part_of_speech: str) -> str:
        if part_of_speech and part_of_speech[0].lower() in 'aeiou':
            return 'an'
        return 'a'

    @staticmethod
    def _extract(entries: Any) -> Optional[dict[str, Any]]:
        # Returns the first usable definition, a usage example (if any definition
        # has one), the origin text (if the API supplies one), and the other
        # parts of speech seen.
        if not isinstance(entries, list):
            return None
        first: Optional[dict[str, Any]] = None
        first_example = ''
        same_pos_example = ''
        any_example = ''
        origin = ''
        other_parts: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if not origin:
                origin = str(entry.get('origin') or '').strip()
            for meaning in entry.get('meanings') or []:
                if not isinstance(meaning, dict):
                    continue
                pos = str(meaning.get('partOfSpeech') or '').strip()
                took_definition = False
                for definition in meaning.get('definitions') or []:
                    if not isinstance(definition, dict):
                        continue
                    text = str(definition.get('definition') or '').strip()
                    if not text:
                        continue
                    example = str(definition.get('example') or '').strip()
                    if first is None:
                        first = {
                            'part_of_speech': pos or 'word',
                            'definition': text,
                        }
                        first_example = example
                        took_definition = True
                    elif not took_definition and pos and pos != first['part_of_speech'] and pos not in other_parts:
                        other_parts.append(pos)
                        took_definition = True
                    # Keep scanning every definition so a later one can supply an example
                    if example:
                        if not any_example:
                            any_example = example
                        if not same_pos_example and (pos or 'word') == first['part_of_speech']:
                            same_pos_example = example
        if first is None:
            return None
        first['example'] = first_example or same_pos_example or any_example
        first['origin'] = origin
        first['other_parts_of_speech'] = other_parts
        return first

    @staticmethod
    def _failure(message: str, details: str) -> CommandResponse:
        return CommandResponse(
            success=False,
            context_data={'message': message},
            error_details=details,
            wait_for_input=False,
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, request_info: RequestInformation, **kwargs: Any) -> CommandResponse:
        try:
            word = self._clean_word(kwargs.get('word'))
            if not word:
                return CommandResponse(
                    success=False,
                    context_data={'message': 'Which word would you like me to define?'},
                    error_details='No valid word provided',
                    wait_for_input=True,
                )

            url = API_URL + quote(word)
            try:
                response = requests.get(
                    url,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    headers={'Accept': 'application/json'},
                )
            except requests.exceptions.Timeout:
                logger.warning('Dictionary API timed out')
                return self._failure(
                    'The dictionary service took too long to respond. Please try again in a moment.',
                    'Request timed out',
                )
            except requests.exceptions.RequestException as exc:
                logger.warning(f'Dictionary API request failed: {exc}')
                return self._failure(
                    "I couldn't reach the dictionary service right now.",
                    f'Request failed: {exc}',
                )

            if response.status_code == 404:
                return CommandResponse.final_response(
                    context_data={
                        'word': word,
                        'found': False,
                        'message': (
                            f"I couldn't find a definition for {word}. "
                            'Double-check the spelling or try another word.'
                        ),
                    }
                )

            if response.status_code != 200:
                logger.warning(f'Dictionary API returned status {response.status_code}')
                return self._failure(
                    'The dictionary service ran into a problem. Please try again later.',
                    f'Unexpected status code {response.status_code}',
                )

            try:
                payload = response.json()
            except ValueError:
                return self._failure(
                    'I got an unreadable answer from the dictionary service.',
                    'Invalid JSON in response',
                )

            result = self._extract(payload)
            if result is None:
                return CommandResponse.final_response(
                    context_data={
                        'word': word,
                        'found': False,
                        'message': f"I couldn't find a definition for {word}.",
                    }
                )

            pos = result['part_of_speech']
            definition = self._shorten(result['definition'])
            article = self._article(pos)
            spoken_definition = self._lower_first(definition)
            message = f'{word.capitalize()} is {article} {pos} meaning: {spoken_definition}.'

            example = self._format_example(result.get('example', ''))
            if example:
                message += f' For example: "{example}"'

            # Etymology: use the API's own origin text when present, otherwise try
            # a best-effort lookup. If neither has anything, it is simply omitted.
            etymology = self._clean_etymology(result.get('origin', ''))
            if not etymology:
                etymology = self._fetch_etymology(word)
            if etymology:
                message += f' Etymology: {etymology}'
                if not etymology.endswith('.'):
                    message += '.'

            return CommandResponse.final_response(
                context_data={
                    'word': word,
                    'found': True,
                    'part_of_speech': pos,
                    'definition': definition,
                    'example': example,
                    'etymology': etymology,
                    'other_parts_of_speech': result['other_parts_of_speech'],
                    'message': message,
                }
            )
        except Exception as exc:  # never raise to the caller
            logger.error(f'define_word failed unexpectedly: {exc}')
            return self._failure(
                'Sorry, something went wrong while looking up that word.',
                str(exc),
            )
