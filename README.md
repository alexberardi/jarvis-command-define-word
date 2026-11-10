# Define Word

A Jarvis voice command that looks up the definition of an English word using the free [Dictionary API](https://dictionaryapi.dev) and speaks a short definition along with the part of speech, a short usage example (when the dictionary has one) and the word's etymology (when one can be found).

## Setup

No setup is required.

- **API key:** none. The dictionaryapi.dev service is free and keyless.
- **Secrets:** none.
- **Python packages:** `requests` (installed automatically with the package).
- **Network:** the node needs outbound internet access to `api.dictionaryapi.dev` and, for etymology fallback lookups, `en.wiktionary.org`.

## Usage

Say things like:

- "What does serendipity mean?"
- "Define ephemeral."
- "What is the definition of ubiquitous?"
- "What is the etymology of scholastic?"
- "Look up the word pragmatic."

Example spoken response:

> Serendipity is a noun meaning: the occurrence of events by chance in a happy or beneficial way. For example: "A fortunate stroke of serendipity brought them together." Etymology: Coined by Horace Walpole in 1754 after a Persian fairy tale.

Every definition answer includes the etymology when one is available, so asking for the "etymology" or "origin" of a word uses this same command.

## Supported actions / behavior

- Looks up a single English word (or short phrase) and speaks the first available definition with its part of speech.
- Adds a short "For example:" usage sentence whenever the dictionary provides one for the word (any of its definitions). If there is no example, the usage sentence is simply left out.
- Adds an "Etymology:" sentence. It uses the `origin` text from dictionaryapi.dev when present; otherwise it makes a short best-effort lookup of the word's English etymology section on [Wiktionary](https://en.wiktionary.org) (text is available under CC BY-SA). If no etymology is found, or that lookup fails or times out, the etymology is simply left out and the rest of the answer is unaffected.
- Etymology text is cleaned for speech: parenthetical notes and words in non-Latin scripts are dropped, and long text is trimmed at a sentence or clause boundary. For words with several etymologies, the first one is used.
- Long definitions and examples are also shortened at a sentence or clause boundary so they stay comfortable to listen to.
- Extra data (the example sentence, etymology and other parts of speech) is included in the response context for follow-up questions.
- **Word not found:** responds politely, e.g. "I couldn't find a definition for blorptastic. Double-check the spelling or try another word."
- **Network problems / timeouts / service errors:** responds with a friendly message instead of failing.
- **No word given:** asks which word you'd like defined.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `word` | string | yes | The word to define |

## License

MIT
