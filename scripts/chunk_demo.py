"""Show how ``chunk_text`` cuts real PL/EN/JP texts at the default limits.

Run: uv run python scripts/chunk_demo.py

For each language the script prints the input size, every chunk with its
length, and a lossless check proving that concatenating the chunks restores
the input exactly. The last block chops the Polish text into small chunks.
"""

from __future__ import annotations

import sys

from anishift.services.translation.chunking import DEFAULT_CHAR_LIMIT, DEFAULT_CHUNK_LIMIT, chunk_text

_TEXT_PL = (
    "Stary zegarmistrz mieszkał przy ul. Długiej od czterdziestu lat. Znali go wszyscy: "
    "dr Nowak, prof. Kowalska, a nawet mjr Wiśniewski z komendy. Naprawiał zegary, budziki, "
    "pozytywki itd. — od świtu do zmierzchu. Mówiono, że potrafi ożywić każdy mechanizm, "
    "np. taki, który przeleżał w piwnicy pół wieku.\n\n"
    "Pewnego ranka do warsztatu weszła dziewczynka z zepsutą pozytywką po babci. Melodia "
    "urywała się w połowie taktu, tzn. dokładnie tam, gdzie sprężyna straciła zaczep. "
    "Zegarmistrz obejrzał mechanizm pod lupą, pokiwał głową i obiecał, że do niedzieli "
    "wszystko zagra jak w 1898. roku, gdy pozytywkę zbudowano.\n\n"
    "Praca zajęła trzy noce. Wymienił zaczep, wyczyścił bębenek, nasmarował ośki itp., "
    "a na końcu nakręcił korbkę i zamknął wieczko. Melodia popłynęła czysto od pierwszego "
    "do ostatniego taktu. Dziewczynka słuchała z zamkniętymi oczami, a stary mistrz "
    "uśmiechał się do siebie, bo wiedział, że takich chwil nie da się naprawić — one po "
    "prostu się zdarzają."
)

_TEXT_EN = (
    "Mr. Tanaka opened the little repair shop on St. Andrews Ave. every morning at six. "
    "His first customer was usually Dr. Reed, who brought broken radios, alarm clocks, "
    "music boxes, etc., and never once asked for a discount. The shop smelled of oil and "
    "old brass, i.e. exactly the way a workshop should smell.\n\n"
    "One winter a girl carried in a music box that had belonged to her grandmother. The "
    "melody stopped in the middle of a bar, right where the spring had lost its hook. "
    "Mr. Tanaka studied the mechanism under a loupe, nodded slowly, and promised it would "
    "sing again by Sunday, just as it had in 1898, when it was built.\n\n"
    "The work took three nights. He replaced the hook, cleaned the barrel, oiled every "
    "axle, and finally wound the crank and closed the lid. The tune flowed clean from the "
    "first note to the last. The girl listened with her eyes closed, and the old craftsman "
    "smiled to himself, because he knew some moments cannot be repaired — they simply happen."
)

_TEXT_JP = (
    "昔々、小さな町に年老いた時計職人が住んでいた。彼の店は駅前の細い路地にあり、壁一面に振り子時計が"
    "掛かっていた。毎朝六時になると、店中の時計がいっせいに鳴り出す。町の人々は「あの音を聞くと一日が"
    "始まる」と言って笑った。\n\n"
    "ある冬の日、ひとりの少女が壊れたオルゴールを抱えて店に入ってきた。祖母の形見だという。メロディは"
    "途中で止まり、ぜんまいの掛かりが外れていた。職人はルーペで機械を覗き込み、静かにうなずいて言った。"
    "「日曜日までには、また歌うようになるよ。」\n\n"
    "修理には三晩かかった。掛かりを直し、円筒を磨き、軸に油を差し、最後にねじを巻いて蓋を閉じた。"
    "メロディは最初の音から最後の音まで澄んで流れた。少女は目を閉じて聴き入り、老いた職人はひとり"
    "微笑んだ。直せない瞬間もある。それはただ、訪れるものだから。"
)

_SMALL_CHAR_LIMIT = 120
_SMALL_CHUNK_LIMIT = 60


def _show(
    label: str, text: str, *, char_limit: int = DEFAULT_CHAR_LIMIT, chunk_limit: int = DEFAULT_CHUNK_LIMIT
) -> None:
    """Chunk one text and print every chunk with its length plus a lossless check."""
    chunks = chunk_text(text, char_limit=char_limit, chunk_limit=chunk_limit)
    print("=" * 70)
    print(f"{label} (input: {len(text)} chars) | char_limit={char_limit}, chunk_limit={chunk_limit}")
    print("=" * 70)
    for number, chunk in enumerate(chunks, start=1):
        print(f"--- chunk {number}/{len(chunks)} ({len(chunk)} chars) ---")
        print(chunk)
    lossless = "".join(chunks) == text
    print(f"lossless check: joined chunks == input -> {lossless}")
    print()
    if not lossless:
        raise SystemExit(1)


def main() -> None:
    """Run the demo at the default limits, then chop a long text into small chunks."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    _show("PL - Polish", _TEXT_PL)
    _show("EN - English", _TEXT_EN)
    _show("JP - Japanese", _TEXT_JP)
    _show("PL - long text, small chunks", _TEXT_PL, char_limit=_SMALL_CHAR_LIMIT, chunk_limit=_SMALL_CHUNK_LIMIT)


if __name__ == "__main__":
    main()
