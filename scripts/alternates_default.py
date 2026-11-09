#!/usr/bin/env python3
"""Делает альтернативы ss01–ss11 формами по умолчанию (вариант «B», выбор владельца 2026-11-09).

Семейство глифа = корень (например, adieresis) + все имена, до которых его доводят ss01–ss11
(adieresis.ss01, adieresis.ss03 и их комбинация). Внутри семейства содержимое переставляется
на дополнение: имя, до которого доводил набор фич S, теперь хранит форму, которую давали все
фичи семейства, кроме S. Поэтому GSUB-лукапы ssXX не трогаем — они начинают работать наоборот
и возвращают классическую (хельветиковскую) форму.

Кернинг, mark и mkmk в features.fea привязаны к именам и подобраны под форму (у альтернатив
свой кернинг и свои якоря), поэтому в GPOS-части имена переставляются вслед за формами.

Составные глифы вне семейств (Ĳ, ǔ, кириллическая І, ʲ ʸ ˡ) ссылаются на те же имена и потому
получают новые формы — так они совпадают со своими базовыми буквами. Исключения — KEEP_CLASSIC.

Повторный запуск ничего не делает: в lib UFO ставится флаг.
Запуск из корня репозитория: .venv/bin/python scripts/alternates_default.py
"""

import copy
import io
import itertools
import re
from pathlib import Path

import ufoLib2
from fontTools.feaLib import ast
from fontTools.feaLib.parser import Parser

ROOT = Path(__file__).resolve().parent.parent
MASTERS = [ROOT / "sources" / "Roman-Light.ufo", ROOT / "sources" / "Roman-Black.ufo"]
FLAG = "com.iamzeny.alternatesDefault"
TAGS = [f"ss{i:02d}" for i in range(1, 12)]
# ɐ (U+0250) в IPA — перевёрнутая двухъярусная a. Собранная из новой однопролётной a,
# она превратилась бы в ɒ — другой звук, поэтому её компоненты остаются классическими.
KEEP_CLASSIC = ["uni0250"]

# После перестановки наборы возвращают старые формы — подписи в меню приложений меняются.
FEATURE_NAMES = {
    "Single-storey 'a'": "Double-storey 'a'",
    "Bottom-curled 'l'": "Straight 'l'",
    "Rounded dots": "Square dots",
    "Spurless 'G'": "Spurred 'G'",
    "Straight-legged 'R'": "Classic 'R'",
    "Alternative 'J'": "Classic 'J'",
    "Alternative 'y'": "Classic 'y'",
    "Arcless 't'": "Arched 't'",
    "Alternative asterisk": "Classic asterisk",
    "Terminal-less 'u'": "Spurred 'u'",
    "Serif 'I'": "Sans-serif 'I'",
}

GLYPH = re.compile(r"\\([A-Za-z0-9_.\-]+)")
LOOKUP = re.compile(r"lookup (\S+) \{.*?\} \1;", re.S)
CLASSDEF = re.compile(r"^(@[\w.\-]+) = \[[^\]]*\];", re.M)


def ss_steps(fea: str, glyph_names: set[str]) -> list[tuple[str, dict[str, str]]]:
    """Одиночные замены ss01–ss11 в порядке лукапов — в этом порядке их применяет шейпер."""
    doc = Parser(io.StringIO(fea), glyphNames=glyph_names).parse()
    order = [s.name for s in doc.statements if isinstance(s, ast.LookupBlock)]
    blocks = {s.name: s for s in doc.statements if isinstance(s, ast.LookupBlock)}
    owner: dict[str, str] = {}
    for st in doc.statements:
        if isinstance(st, ast.FeatureBlock) and st.name in TAGS:
            for ref in st.statements:
                if isinstance(ref, ast.LookupReferenceStatement):
                    owner[ref.lookup.name] = st.name
    steps = []
    for name in order:
        if name not in owner:
            continue
        mapping: dict[str, str] = {}
        for st in blocks[name].statements:
            if isinstance(st, ast.SingleSubstStatement):
                src = list(st.glyphs[0].glyphSet())
                dst = list(st.replacements[0].glyphSet())
                mapping.update(zip(src, dst * len(src) if len(dst) == 1 else dst))
            elif not isinstance(st, (ast.Comment, ast.LookupFlagStatement)):
                raise SystemExit(f"{name}: неожиданное правило {type(st).__name__}")
        steps.append((owner[name], mapping))
    return steps


def complement_map(steps: list[tuple[str, dict[str, str]]]) -> dict[str, str]:
    """σ: имя → имя, чьё старое содержимое оно должно получить (инволюция внутри семейства)."""
    sources = {g for _, m in steps for g in m}
    targets = {g for _, m in steps for g in m.values()}
    sigma: dict[str, str] = {}
    for root in sorted(sources - targets):
        reach, frontier = {root}, [root]
        while frontier:
            g = frontier.pop()
            for _, m in steps:
                if g in m and m[g] not in reach:
                    reach.add(m[g])
                    frontier.append(m[g])
        tags = sorted({t for t, m in steps if reach & m.keys()})
        state: dict[frozenset[str], str] = {}
        for k in range(len(tags) + 1):
            for subset in itertools.combinations(tags, k):
                g = root
                for t, m in steps:
                    if t in subset:
                        g = m.get(g, g)
                state[frozenset(subset)] = g
        # Перестановка корректна, только если каждая комбинация фич даёт свой глиф.
        if len(set(state.values())) != len(state) or set(state.values()) != reach:
            raise SystemExit(f"семейство {root}: неполная решётка {state}")
        full = frozenset(tags)
        for subset, g in state.items():
            if g in sigma:
                raise SystemExit(f"{g} попал в два семейства")
            sigma[g] = state[full - subset]
    return sigma


def rename_gpos(fea: str, sigma: dict[str, str]) -> str:
    """Переставляет имена во всём, кроме GSUB-лукапов и классов, которые они используют."""
    gsub_spans = [m.span() for m in LOOKUP.finditer(fea) if re.search(r"^\s*(r?sub|ignore sub) ", m.group(0), re.M)]
    gsub_text = "".join(fea[a:b] for a, b in gsub_spans)
    gsub_classes = set(re.findall(r"@[\w.\-]+", gsub_text))
    frozen = gsub_spans + [m.span() for m in CLASSDEF.finditer(fea) if m.group(1) in gsub_classes]
    frozen.sort()
    out, pos = [], 0

    def swap(m: re.Match[str]) -> str:
        name = m.group(1) or ""
        return "\\" + sigma.get(name, name)

    for a, b in frozen:
        out.append(GLYPH.sub(swap, fea[pos:a]))
        out.append(fea[a:b])
        pos = b
    out.append(GLYPH.sub(swap, fea[pos:]))
    return "".join(out)


def apply(path: Path, sigma: dict[str, str]) -> None:
    font = ufoLib2.Font.open(path)
    old = {name: copy.deepcopy(font[name]) for name in sigma}
    layer = font.layers.defaultLayer
    for name, src_name in sigma.items():
        glyph = copy.deepcopy(old[src_name])
        glyph.unicodes = list(old[name].unicodes)
        # Компоненты переехавшей формы указывают на свои состояния — переводим их вслед за σ.
        for comp in glyph.components:
            comp.baseGlyph = sigma.get(comp.baseGlyph, comp.baseGlyph)
        layer.insertGlyph(glyph, name=name, overwrite=True, copy=False)
    for name in KEEP_CLASSIC:
        for comp in font[name].components:
            comp.baseGlyph = sigma.get(comp.baseGlyph, comp.baseGlyph)
    fea = rename_gpos(font.features.text, sigma)
    for before, after in FEATURE_NAMES.items():
        if f'"{before}"' not in fea:
            raise SystemExit(f"{path.name}: нет подписи набора {before!r}")
        fea = fea.replace(f'"{before}"', f'"{after}"')
    font.features.text = fea
    font.lib[FLAG] = True
    font.save(path, overwrite=True)


def main() -> None:
    fonts = [ufoLib2.Font.open(p) for p in MASTERS]
    if all(f.lib.get(FLAG) for f in fonts):
        print("уже применено")
        return
    if any(f.lib.get(FLAG) for f in fonts):
        raise SystemExit("флаг стоит только в одном мастере — восстановите sources/ и запустите заново")
    sigmas = [complement_map(ss_steps(f.features.text, set(f.keys()))) for f in fonts]
    if sigmas[0] != sigmas[1]:
        raise SystemExit("наборы ss01–ss11 в мастерах различаются")
    sigma = sigmas[0]
    for path in MASTERS:
        apply(path, sigma)
    print(f"переставлено глифов: {len(sigma)}")


if __name__ == "__main__":
    main()
