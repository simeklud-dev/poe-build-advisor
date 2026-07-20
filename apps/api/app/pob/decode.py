"""Dekódování Path of Building export kódů (url-safe base64 + zlib -> XML).

Zkopírováno z `poe-build-finder/apps/api/app/pob/decode.py` (stejný projekt,
stejná logika, nemá cenu ji psát znovu) a ověřeno proti Lua zdrojákům PoB
(`src/Modules/Main.lua:74` decode, `src/Modules/Build.lua:1463` encode) --
viz AI_BUILD_ADVISOR_PLAN.md v projektu "POE Build helper".

Tento modul NIKDY sám nic nestahuje z pobb.in/pastebin.com/poe.ninja --
pracuje jen s kódem, který mu někdo přímo dodá (uživatel v chatu). Jejich
`robots.txt` výslovně zakazuje endpointy potřebné pro programové stažení
(`/raw`, `/api/`, `/json`), takže je nefetchujeme.

Poznámka k headless PoB enginu: `Deflate`/`Inflate` v `HeadlessWrapper.lua`
jsou jen prázdné TODO stuby (skutečná komprese je v kompilované runtime
knihovně, kterou headless prostředí nemá) -- proto se (de)komprese kódu
řeší tady v Pythonu (`zlib`), a do/z Lua bridge (`pob-bridge.lua`) chodí
vždy jen čisté XML, nikdy komprimovaný kód.
"""

import base64
import zlib


def decode_pob_code(code: str) -> str:
    """Vrátí XML string. Vyhodí výjimku (ValueError/zlib.error), pokud kód není platný."""
    stripped = code.strip()
    padding = "=" * (-len(stripped) % 4)
    raw = base64.urlsafe_b64decode(stripped + padding)
    return zlib.decompress(raw).decode("utf-8")


def encode_pob_code(xml: str) -> str:
    """Opak `decode_pob_code` -- používá se pro `export_xml` z bridge a v testech pro round-trip."""
    compressed = zlib.compress(xml.encode("utf-8"))
    return base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
