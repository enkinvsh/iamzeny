#!/usr/bin/env python3
"""Сборка семейства из sources/: имена → designspace → variable TTF + статика OTF/TTF/WOFF2.

Запуск из корня репозитория: .venv/bin/python scripts/build.py
Повторный запуск даёт тот же результат: имена перезаписываются, fonts/ собирается заново.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import ufoLib2
from fontTools.designspaceLib import (
    AxisDescriptor,
    DesignSpaceDocument,
    InstanceDescriptor,
    SourceDescriptor,
)
from fontTools.ttLib import TTFont

# Переименование семейства = правка этих двух строк и перезапуск.
FAMILY = "iamzeny"
VERSION = (0, 100)

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
FONTS = ROOT / "fonts"
DESIGNSPACE = SOURCES / "Roman.designspace"
PS_FAMILY = FAMILY.replace(" ", "")

# OFL требует сохранить исходный копирайт (строки совпадают с OFL.txt). Имя «Overused Grotesk»
# в релизе v0.5-alpha.2 было Reserved Font Name — поэтому в метаданных форка его нет, только автор.
COPYRIGHT = (
    "Copyright 2023-2026 Bao Nguyen (RandomMaerks); "
    f"Copyright 2026 The {FAMILY} Project Authors"
)
LICENSE = (
    "This Font Software is licensed under the SIL Open Font License, Version 1.1. "
    "This license is available with a FAQ at: https://openfontlicense.org"
)

MASTERS = {"Light": 300, "Black": 900}
# Шкала толщин унаследована от legacy-designspace Overused Grotesk:
# пользовательское значение wght → координата в дизайне.
WEIGHT_MAP = [(300, 300), (350, 375), (400, 450), (500, 525), (600, 610), (700, 710), (800, 800), (900, 900)]
INSTANCES = [
    ("Light", 300), ("Book", 375), ("Regular", 450), ("Medium", 525),
    ("SemiBold", 610), ("Bold", 710), ("ExtraBold", 800), ("Black", 900),
]


def set_names() -> None:
    for style in MASTERS:
        path = SOURCES / f"Roman-{style}.ufo"
        font = ufoLib2.Font.open(path)
        info = font.info
        info.familyName = FAMILY
        info.styleMapFamilyName = f"{FAMILY} {style}"
        info.styleMapStyleName = "regular"
        info.postscriptFontName = f"{PS_FAMILY}-{style}"
        info.postscriptFullName = f"{FAMILY} {style}"
        info.versionMajor, info.versionMinor = VERSION
        info.openTypeNameVersion = f"Version {VERSION[0]}.{VERSION[1]:03d}"
        info.copyright = COPYRIGHT
        info.openTypeNameLicense = LICENSE
        info.openTypeNameLicenseURL = "https://openfontlicense.org"
        info.openTypeNameDesigner = "Bao Nguyen (RandomMaerks), zeny"
        info.openTypeNameManufacturer = "zeny"
        info.openTypeOS2VendorID = "ZENY"
        info.trademark = None
        font.save(path, overwrite=True)


def write_designspace() -> None:
    doc = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.name, axis.tag = "weight", "wght"
    axis.minimum, axis.default, axis.maximum = 300, 300, 900
    axis.map = WEIGHT_MAP
    doc.addAxis(axis)
    for style, wght in MASTERS.items():
        src = SourceDescriptor()
        src.filename = f"Roman-{style}.ufo"
        src.familyName, src.styleName = FAMILY, style
        src.location = {"weight": wght}
        doc.addSource(src)
    for style, wght in INSTANCES:
        inst = InstanceDescriptor()
        inst.familyName, inst.styleName = FAMILY, style
        inst.postScriptFontName = f"{PS_FAMILY}-{style}"
        inst.filename = f"instances/{PS_FAMILY}-{style}.ufo"
        inst.location = {"weight": wght}
        # Пара Regular/Bold — основное семейство для старых меню (RIBBI), остальные — отдельные подсемейства.
        if style in ("Regular", "Bold"):
            inst.styleMapFamilyName, inst.styleMapStyleName = FAMILY, style.lower()
        else:
            inst.styleMapFamilyName, inst.styleMapStyleName = f"{FAMILY} {style}", "regular"
        doc.addInstance(inst)
    doc.write(DESIGNSPACE)


def fontmake(*args: str) -> None:
    cmd = [sys.executable, "-m", "fontmake", "-m", str(DESIGNSPACE), *args]
    subprocess.run(cmd, check=True, cwd=ROOT)


def build() -> None:
    shutil.rmtree(FONTS, ignore_errors=True)
    shutil.rmtree(SOURCES / "instances", ignore_errors=True)
    fontmake("-o", "variable", "--output-path", str(FONTS / "variable" / f"{PS_FAMILY}[wght].ttf"))
    fontmake("-i", "-o", "otf", "--output-dir", str(FONTS / "otf"))
    fontmake("-i", "-o", "ttf", "--output-dir", str(FONTS / "ttf"))
    (FONTS / "woff2").mkdir(parents=True)
    for ttf in [*sorted((FONTS / "ttf").glob("*.ttf")), *sorted((FONTS / "variable").glob("*.ttf"))]:
        font = TTFont(ttf)
        font.flavor = "woff2"
        font.save(FONTS / "woff2" / ttf.with_suffix(".woff2").name)
    shutil.rmtree(SOURCES / "instances", ignore_errors=True)


if __name__ == "__main__":
    set_names()
    write_designspace()
    build()
