# EVSE firmware

Obrazy firmware pro nabíjecí stanici **chargebyte EVSE** (komunikační deska
ESP32-S3, řídicí STM32 a modul chargebyte CME). Stanice si je stahuje sama
a aktualizace se spouští ručně ze stránky **Firmware** v aplikaci IoTMeter.

Repo obsahuje jen hotové obrazy a `manifest.json`. Zdrojové kódy jsou
v soukromém repu `Vilmio/chargebyte_evse`.

## Obsah

| Soubor | Co to je | Verze |
|---|---|---|
| `manifest.json` | seznam obrazů, verzí, velikostí a SHA-256 | – |
| `stm32_<verze>.bin` | aplikace STM32F303 (od 0x08005000, bez bootloaderu) | `FW_VERSION` v `firmware/cme_evse/Core/Inc/config.h`, registr 101 |
| `cme_<verze>_<varianta>.srec` | šifrovaný firmware chargebyte CME | release chargebyte, registr 3030+ |
| `esp_<verze>.bin` | aplikace ESP32 pro OTA (`micropython.bin`, ne `firmware.bin`) | `VERSION` v `ESP32_APP/backend/version.py` |

Aktuálně: STM32 **1**, CME **2.4.2** (`DIN_AC2_DC2_NO-TLS`). ESP obraz zatím
není - stanice s ESP 0.1.0 tedy ESP aktualizaci nenabídne.

## Odkud si to stanice bere

Nastavení `UPDATE_URL` na ESP (výchozí hodnota):

```
https://github.com/Vilmio/evse-firmware/releases/latest/download/manifest.json
```

- `releases/latest` = poslední release označený jako **Latest**. Pre-release
  se nepočítá, takže se na něm dá nový firmware vyzkoušet: testovací stanici
  nastavte `.../releases/download/<tag>/manifest.json`.
- `url` v manifestu je relativní vůči adrese manifestu, takže všechny soubory
  musí být **assety téhož release**.
- `latest/download` vidí jen soubory posledního release - **každý release musí
  obsahovat všechny obrazy**, i ty, které se nezměnily. Stanice porovná verze
  a nabídne jen novější.

## Formát manifestu

```json
{
  "esp":   {"version": "0.2.0", "url": "esp_0.2.0.bin", "size": 1728752, "sha256": "..."},
  "stm32": {"version": 1, "url": "stm32_1.bin", "size": 41396, "sha256": "..."},
  "cme":   {"version": "2.4.2", "min_bootloader": 15,
            "variants": {"DIN_AC2_DC2_NO-TLS": {"url": "cme_2.4.2_DIN_AC2_DC2_NO-TLS.srec",
                                                "size": 1090765, "sha256": "..."}}}
}
```

- `esp.version` je text (`"0.2.0"`), `stm32.version` celé číslo, `cme.version` `"x.y.z"`.
  Aktualizace se nabídne, jen když je verze v manifestu **vyšší** než ve stanici.
- `cme.variants` - klíč musí odpovídat nastavení `CME_VARIANT` na ESP
  (výchozí `DIN_AC2_DC2_NO-TLS`). Stanice s jinou variantou CME aktualizaci nenabídne.
- `cme.min_bootloader` - nejnižší verze bootloaderu CME, se kterou update poběží.
- Každá část je volitelná.

Manifest neupravujte ručně - `size` a `sha256` musí sedět přesně, jinak ESP
stažený obraz odmítne.

## Vydání nové verze

1. **Zvyšte verzi** toho, co se mění:
   - STM32: `FW_VERSION` v `firmware/cme_evse/Core/Inc/config.h`, pak build
     **Release** v STM32CubeIDE,
   - ESP: `VERSION` v `ESP32_APP/backend/version.py`, pak `make firmware`,
   - CME: nový release od chargebyte.
2. **Vygenerujte obrazy a manifest** do tohoto repa (z `chargebyte_evse/ESP32_APP`):

   ```bash
   python3 tools/make_release.py --out ../../evse-firmware \
       --esp <micropython>/ports/esp32/build-CHARGEBYTE_EVSE_S3/micropython.bin \
       --stm32 ../firmware/cme_evse/Release/cme_evse.bin --stm32-version 2 \
       --cme "../firmware/FW Release 2.4.2/chargebyte_CME-CCF_release_files_v2.4.2_0f0eeb2"
   ```

   Vždy předejte **všechny tři** obrazy. Starší soubory s jinou verzí v názvu
   z repa smažte.
3. **Commit a tag:**

   ```bash
   git add -A && git commit -m "STM32 2, CME 2.4.2, ESP 0.2.0"
   git tag v2026.09.1 && git push && git push --tags
   ```

4. **GitHub Release** k tagu - na webu *Releases → Draft a new release*, vybrat
   tag a přetáhnout `manifest.json` a všechny obrazy jako assety. Nebo přes
   GitHub CLI:

   ```bash
   gh release create v2026.09.1 manifest.json *.bin *.srec --title "v2026.09.1" --notes "..."
   ```

   Pro test nejdřív s `--prerelease`, po ověření na stanici přepnout na Latest.

## Upozornění

- **STM32 update přeruší nabíjení** - stanice ho nepustí, dokud je připojené
  vozidlo. CME update trvá jednotky minut.
- ESP zatím neověřuje certifikát HTTPS. Obsah obrazů chrání SHA-256
  z manifestu, samotný manifest zatím podepsaný není.
- Firmware CME je majetkem chargebyte GmbH a je šířen šifrovaný. Před
  zveřejněním repa ověřte, že je jeho veřejné šíření povolené.
