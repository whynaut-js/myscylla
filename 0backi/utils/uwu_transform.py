import random
import re

EMOJI_TAG_RE = re.compile(r"<a?:\w+:\d+>")

_SUFFIXES = [
    "nya~", "!!", "??", "*tail wag*", "*chaos*", "*static*", "hehe~",
    "*vibrating at 300hz*", "*feral screeching*", "*unhinged giggle*",
    "*spins violently*", "*ascends*", "*combusts*", "AAAAAA", "!!1!",
    "*chaotic evil energy*", "*gremlin noises*", "*short circuits*",
]

_TWISTS = [
    "eepy", "bwep", "smol brain moment", "chaos incarnate", "vibing rn",
    "no thoughts head empty", "certified gremlin behavior",
    "unhinged and proud", "feral little guy moment", "system malfunction",
    "brain.exe stopped working", "running on 3 brain cells and vibes",
    "certified menace to society", "unregistered chaos entity",
]

_SPARKLES = ["✨", "💥", "⚡", "🌀", "☄️", "🔥", "💫", "🌪️"]

_KEYBOARD_SMASH = [
    "asdkjfhaksjdf", "ajksdhfjkashdf", "wjefiojwef", "kjshdfkjhsdf",
    "aaaaaaaaaa", "AKJSDHFKJASHD", "??!!??!!", "8383838383",
]

_NUCLEAR_CHAOS = [
    "SYSTEM OVERWHELMED BY CHAOS ENERGY, TRANSMISSION LOST",
    "*the message ascends into pure static and is never seen again*",
    "ERROR: TOO MUCH FERAL ENERGY DETECTED, MESSAGE REJECTED BY REALITY ITSELF",
    "*a gremlin ate this message before it could be sent*",
    "REDACTED BY THE UWU COUNCIL FOR EXCESSIVE CHAOS",
]

LINK_EXCUSES = [
    "uwu i naught uuuees lwnks uwu",
    "winks? nuu nuu nuu, bwocked by da vibes~",
    "no wink fow u, onwy chaos awoud~",
    "wink dewetected, sewf destwuct in 3..2..1~ 💥",
    "dat's a paddwin' wink, DENIED uwu",
    "LINK REJECTED BY THE CHAOS FIREWALL ⚡",
    "aksjdhf NO LINKS ALLOWED aksjdhf 🌀",
    "the council has vetoed this link unanimously",
]

GIF_CAPTIONS = [
    "*chaos noises intensify*",
    "certified feral moment, no notes",
    "the goobly wobbly has been unweashed",
    "sir this is a wendy's and yet here we are",
    "bwo posted the ancient scroll of nonsense",
    "unexplainable phenomenon detected, send help",
    "THE PROPHECY HAS BEEN FULFILLED",
    "*entire nervous system short circuits watching this*",
    "this gif has been classified as a biohazard",
    "someone alert the authorities immediately",
]

STICKER_CAPTIONS = [
    "sent a sacred sticker of pure chaos",
    "unleashed a legendary sticker upon this land",
    "the sticker gods have spoken",
    "sticker energy: immaculate",
    "SUMMONED FROM THE STICKER REALM ITSELF",
    "this sticker has been passed down for generations",
]


def _stutter(word: str) -> str:
    if len(word) < 2 or not word[0].isalpha():
        return word
    return f"{word[0]}-{word[0]}-{word}"


def _scream_case(word: str) -> str:
    return word.upper()


def uwu_transform(text: str) -> str:
    if not text:
        return text

    # rare nuclear option — the whole message just becomes chaos
    if random.random() < 0.05:
        return random.choice(_NUCLEAR_CHAOS)

    placeholders = {}

    def _stash(match):
        key = f"\u00a7{len(placeholders)}\u00a7"
        placeholders[key] = match.group(0)
        return key

    protected = EMOJI_TAG_RE.sub(_stash, text)

    protected = re.sub(r"[rl]", "w", protected)
    protected = re.sub(r"[RL]", "W", protected)
    protected = protected.replace("th", "d").replace("Th", "D")
    protected = protected.replace("ove", "uv")
    protected = re.sub(r"n([aeiou])", r"ny\1", protected)

    words = protected.split(" ")
    for i, word in enumerate(words):
        if not word:
            continue
        roll = random.random()
        if roll < 0.12:
            words[i] = _stutter(word)
        elif roll < 0.18:
            words[i] = _scream_case(word)
    protected = " ".join(words)

    if random.random() < 0.4:
        protected += f" {random.choice(_SUFFIXES)}"
    if random.random() < 0.3:
        protected += f" ({random.choice(_TWISTS)})"
    if random.random() < 0.35:
        sparkle_count = random.randint(1, 3)
        protected += " " + "".join(random.choices(_SPARKLES, k=sparkle_count))
    if random.random() < 0.1:
        protected += f" {random.choice(_KEYBOARD_SMASH)}"

    for key, original in placeholders.items():
        protected = protected.replace(key, original)

    return protected


def random_link_excuse() -> str:
    return random.choice(LINK_EXCUSES)


def random_gif_caption() -> str:
    return random.choice(GIF_CAPTIONS)


def random_sticker_caption(sticker_name: str) -> str:
    return f"{random.choice(STICKER_CAPTIONS)} ({sticker_name})"
