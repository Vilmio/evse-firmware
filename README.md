# EVSE firmware

Obrazy firmware pro nabíjecí stanici **chargebyte EVSE** (komunikační deska
ESP32-S3, řídicí STM32 a modul chargebyte CME). Stanice si je stahuje sama
a aktualizace se spouští ručně ze stránky **Firmware** v aplikaci IoTMeter.

Repo obsahuje jen hotové obrazy a soubor `firmware.toml` s jejich verzemi;
`manifest.json` a release vytváří GitHub Actions po pushnutí tagu. Zdrojové kódy
jsou v soukromém repu `Vilmio/chargebyte_evse`.

## Obsah

| Soubor | Co to je |
|---|---|
| `firmware.toml` | **aktuální verze a soubory ve vydání - upravuje se ručně** |
| `stm32_<verze>.bin` | aplikace STM32F303 (od 0x08005000, bez bootloaderu), verze = `FW_VERSION` v `firmware/cme_evse/Core/Inc/config.h` (registr 101) |
| `cme_<verze>_<varianta>.srec` | šifrovaný firmware chargebyte CME |
| `esp_<verze>.bin` | aplikace ESP32 pro OTA (`micropython.bin`, ne `firmware.bin`), verze = `VERSION` v `ESP32_APP/backend/version.py` |
| `tools/build_manifest.py` | z `firmware.toml` vytvoří `dist/` s `manifest.json` a obrazy, zkontroluje je |
| `.github/workflows/release.yml` | po pushnutí tagu `v*` sestaví a vydá GitHub Release |
| `.github/workflows/prune.yml`, `tools/prune_releases.sh` | po vydání ponechá jen poslední 3 tagy a releasy |

`manifest.json` se do repa necommituje - generuje se při každém vydání.

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

## Vydání nové verze

1. **Nahraďte obraz** v kořeni repa (starý smažte) a **zvyšte verzi**:
   - STM32: `FW_VERSION` v `config.h`, build **Release** v STM32CubeIDE, soubor `stm32_<verze>.bin`,
   - ESP: `VERSION` v `backend/version.py`, `make firmware`, soubor `esp_<verze>.bin` z `micropython.bin`,
   - CME: nový `.srec` od chargebyte.
2. **Upravte `firmware.toml`** - verzi a název souboru.
3. **Zkontrolujte na počítači** (Python 3.11+):

   ```bash
   python3 tools/build_manifest.py
   ```

4. **Commit, tag, push:**

   ```bash
   git add -A && git commit -m "STM32 3"
   git push
   git tag v0.0.3 && git push origin v0.0.3
   ```

5. GitHub Actions (záložka **Actions**) vygeneruje `manifest.json`, zkontroluje obrazy
   a vytvoří **Release** se všemi soubory. Za ~1 minutu je k dispozici stanicím.

**Testovací vydání:** tag s pomlčkou (`v0.0.3-rc1`) se vydá jako **pre-release** -
`releases/latest` na něj neukazuje, stanice ho nestáhnou. Testovací stanici nastavte
`UPDATE_URL` na `https://github.com/Vilmio/evse-firmware/releases/download/v0.0.3-rc1/manifest.json`.
Po ověření vydejte stejný obsah s normálním tagem.

**Úklid:** po každém úspěšném vydání akce *Prune releases* ponechá jen **poslední 3 tagy
a jejich releasy** (podle čísla verze), starší smaže i s tagem. Release označený jako
**Latest se nesmaže nikdy**, ani když ho předběhnou novější pre-releasy. Ručně: *Actions →
Prune releases → Run workflow* (počet a „dry run“ jen pro výpis). Lokálně bez mazání:
`KEEP=3 DRY_RUN=1 GH_REPO=Vilmio/evse-firmware tools/prune_releases.sh` (potřebuje `gh`).

**Kontroly při vydání** (release se nevytvoří, chyba je v logu Actions):
- soubor existuje a má správný formát: ESP obraz `0xE9`, STM32 vektorová tabulka pro 0x08005000, CME S-record,
- obraz se vejde do paměti (ESP OTA oddíl 4 MB, STM32 104 KB),
- verze má správný typ, název `.srec` obsahuje verzi CME,
- oproti poslednímu release: žádná verze neklesla, **změněný soubor má vyšší verzi**
  a nechybí žádný obraz.

Release **nevytvářejte ručně na webu** - tag vytvořený přes web Actions nespustí
a manifest by chyběl. Když se vydání nepovede nebo tag ukazuje na chybný commit:
opravte, smažte tag (`git tag -d v0.0.3 && git push --delete origin v0.0.3`) a pushněte
ho znovu. Existující release se tím přepíše novými soubory (`--clobber`).

## Formát manifestu

Generuje ho `tools/build_manifest.py`, čte `ESP32_APP/backend/fw/updater.py`:

```json
{
  "esp":   {"version": "0.2.0", "url": "esp_0.2.0.bin", "size": 1728752, "sha256": "..."},
  "stm32": {"version": 2, "url": "stm32_2.bin", "size": 41492, "sha256": "..."},
  "cme":   {"version": "2.4.2", "min_bootloader": 15,
            "variants": {"DIN_AC2_DC2_NO-TLS": {"url": "cme_2.4.2_DIN_AC2_DC2_NO-TLS.srec",
                                                "size": 1090765, "sha256": "..."}}}
}
```

- Aktualizace se nabídne, jen když je verze v manifestu **vyšší** než ve stanici.
- Klíč varianty CME musí odpovídat `CME_VARIANT` na ESP (výchozí `DIN_AC2_DC2_NO-TLS`).
- ESP stažený obraz odmítne, když nesedí `size` nebo `sha256`.

## Upozornění

- **STM32 update přeruší nabíjení** - stanice ho nepustí, dokud je připojené
  vozidlo. CME update trvá jednotky minut.
- ESP zatím neověřuje certifikát HTTPS. Obsah obrazů chrání SHA-256
  z manifestu, samotný manifest zatím podepsaný není.
- Firmware CME je majetkem chargebyte GmbH a je šířen šifrovaný. Před
  zveřejněním repa ověřte, že je jeho veřejné šíření povolené.
