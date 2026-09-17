#!/usr/bin/env python3
"""Z firmware.toml vytvori dist/ s manifest.json a obrazy pro GitHub Release.

    python3 tools/build_manifest.py                      # nahled a kontrola
    python3 tools/build_manifest.py --previous old.json  # + porovnani s minulym releasem

Kontroluje:
- soubory existuji a maji platny format (ESP obraz 0xE9, STM32 vektorova tabulka, S-record),
- velikosti se vejdou do cilove pameti,
- verze maji spravny typ,
- oproti minulemu manifestu: verze neklesla a zmeneny soubor ma vyssi verzi.

Format manifestu cte ESP32_APP/backend/fw/updater.py - pri zmene upravit oba.
Vyzaduje Python 3.11+ (tomllib), bez dalsich zavislosti.
"""
import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
import tomllib
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]

ESP_OTA_PARTITION = 0x400000            # ESP32_APP/board/.../partitions-16MiB-ota.csv
STM32_APP_START = 0x08005000            # cme_evse STM32F303xC_FLASH.ld
STM32_APP_SIZE = 104 * 1024
STM32_RAM = (0x20000000, 0x20000000 + 32 * 1024)   # RAM 32K, CCMRAM zvlast
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class ReleaseError(Exception):
    pass


def parse_version(v) -> tuple:
    """Stejne porovnani jako na ESP (updater.parse_version)."""
    if isinstance(v, int):
        return (v,)
    return tuple(int(part) for part in str(v).split("."))


def image(name: str) -> tuple[Path, bytes]:
    path = REPO_DIR / name
    if "/" in name or not path.is_file():
        raise ReleaseError("file not found in the repository root: {}".format(name))
    return path, path.read_bytes()


def entry(data: bytes, name: str) -> dict:
    return {"url": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def check_esp(section: dict) -> dict:
    version = section.get("version")
    if not isinstance(version, str) or not SEMVER.match(version):
        raise ReleaseError("esp.version must be \"x.y.z\" (backend/version.py)")
    _, data = image(section.get("file", ""))
    if data[:1] != b"\xe9":
        raise ReleaseError("esp.file is not an ESP32 application image (use micropython.bin, not firmware.bin)")
    if len(data) > ESP_OTA_PARTITION:
        raise ReleaseError("esp.file {} B does not fit the OTA partition".format(len(data)))
    return dict(version=version, **entry(data, section["file"]))


def check_stm32(section: dict) -> dict:
    version = section.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or not 0 < version < 0x10000:
        raise ReleaseError("stm32.version must be an integer 1..65535 (FW_VERSION in config.h)")
    _, data = image(section.get("file", ""))
    if len(data) < 8 or len(data) > STM32_APP_SIZE:
        raise ReleaseError("stm32.file {} B does not fit the application area ({} B)".format(len(data), STM32_APP_SIZE))
    stack, reset = struct.unpack_from("<II", data)
    if not (STM32_RAM[0] < stack <= STM32_RAM[1]) or not (STM32_APP_START < reset < STM32_APP_START + len(data)):
        raise ReleaseError("stm32.file is not an application linked at 0x{:08X} (stack 0x{:08X}, reset 0x{:08X})"
                           .format(STM32_APP_START, stack, reset))
    return dict(version=version, **entry(data, section["file"]))


def check_cme(section: dict) -> dict:
    version = section.get("version")
    if not isinstance(version, str) or not SEMVER.match(version):
        raise ReleaseError("cme.version must be \"x.y.z\"")
    min_bootloader = section.get("min_bootloader")
    if not isinstance(min_bootloader, int):
        raise ReleaseError("cme.min_bootloader must be an integer")
    variants = section.get("variants")
    if not isinstance(variants, dict) or not variants:
        raise ReleaseError("cme.variants must list at least one variant")
    out = {}
    for variant, name in variants.items():
        _, data = image(name)
        if not data.startswith(b"S0"):
            raise ReleaseError("cme variant {}: {} is not an S-record file".format(variant, name))
        if version not in name:
            raise ReleaseError("cme variant {}: file name {} does not contain version {}".format(variant, name, version))
        out[variant] = entry(data, name)
    return {"version": version, "min_bootloader": min_bootloader, "variants": out}


def files_of(target: str, item: dict) -> dict:
    """{nazev varianty nebo cile: (verze, sha256)} pro porovnani s minulym releasem."""
    if target == "cme":
        return {"cme " + k: (item["version"], v["sha256"]) for k, v in item.get("variants", {}).items()}
    return {target: (item["version"], item["sha256"])}


def compare(previous: dict, manifest: dict) -> list[str]:
    errors = []
    for target, item in manifest.items():
        if target not in previous:
            continue
        old_version = previous[target].get("version")
        if parse_version(item["version"]) < parse_version(old_version):
            errors.append("{}: version {} is lower than the previous release {}".format(
                target, item["version"], old_version))
        old_files = files_of(target, previous[target])
        for key, (version, sha) in files_of(target, item).items():
            if key in old_files and old_files[key][1] != sha and \
                    parse_version(version) <= parse_version(old_files[key][0]):
                errors.append("{}: file changed but version {} was not raised (previous {})".format(
                    key, version, old_files[key][0]))
    for target in previous:
        if target not in manifest:
            errors.append("{}: missing - every release must contain all images".format(target))
    return errors


def build(config: dict) -> dict:
    checks = {"stm32": check_stm32, "cme": check_cme, "esp": check_esp}
    unknown = set(config) - set(checks)
    if unknown:
        raise ReleaseError("unknown section(s) in firmware.toml: {}".format(", ".join(sorted(unknown))))
    manifest = {target: checks[target](config[target]) for target in ("esp", "stm32", "cme") if target in config}
    if not manifest:
        raise ReleaseError("firmware.toml lists no firmware")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=REPO_DIR / "firmware.toml")
    p.add_argument("--out", type=Path, default=REPO_DIR / "dist")
    p.add_argument("--previous", type=Path, help="manifest.json of the previous release")
    args = p.parse_args()

    try:
        with args.config.open("rb") as f:
            manifest = build(tomllib.load(f))
        if args.previous and args.previous.is_file():
            errors = compare(json.loads(args.previous.read_text()), manifest)
            if errors:
                raise ReleaseError("compared with the previous release:\n  " + "\n  ".join(errors))
    except (ReleaseError, tomllib.TOMLDecodeError) as e:
        print("ERROR: {}".format(e), file=sys.stderr)
        return 1

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    names = [manifest[t]["url"] for t in ("esp", "stm32") if t in manifest]
    names += [v["url"] for v in manifest.get("cme", {}).get("variants", {}).values()]
    for name in names:
        shutil.copyfile(REPO_DIR / name, args.out / name)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    print("-> {}: manifest.json + {}".format(args.out, ", ".join(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
