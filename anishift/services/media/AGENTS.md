# media

Neutralna granica identyfikacji kontenerów MKV i MP4. Zwraca wspólny `MediaCatalog`; nie wybiera ścieżek, nie ekstrahuje i nie podejmuje decyzji produktu.

## Pliki

- `probe.py` — publiczny protokół i dispatcher po rozszerzeniu
- `mkv.py` — adapter `mkvmerge -J` oraz mapowanie legacy `MediaInfo`
- `mp4.py` — adapter `ffprobe` i mapowanie streamów JSON
- `types.py` — neutralny katalog, rodzaje i ścieżki
- `_process.py` — kontrolowany subprocess z timeoutem i anulowaniem
- `_errors.py` — mapowanie awarii procesu i payloadu na błędy domenowe

## Inwarianty

- `MediaProbe.identify` zawsze otrzymuje jawny token anulowania i timeout; adapter musi przekazać oba do runnera.
- Obsługiwane źródła to wyłącznie `.mkv` i `.mp4`; inne rozszerzenie kończy się `UnsupportedMediaError`.
- Probe niczego nie zapisuje i nie pozostawia otwartych zasobów. Nie wolno uruchamiać procesu przez shell.
- MKV zachowuje attachments i flagi default/forced; MP4 mapuje napisy `mov_text`/`tx3g` na docelowy format SRT.
- Błąd startu, timeout, anulowanie, niezerowy exit i uszkodzony JSON są kontrolowanymi `MediaProbeError`, nigdy surowym błędem subprocess/JSON.

## Testy

```bash
uv run pytest tests/services/media -v
```
