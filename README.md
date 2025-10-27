# Zadanie rekrutacyjne, AGH Space Systems Rocket Software jesień 2025

## Setup środowiska wirtualnego

### Instalacja

Do stworzenia wirtualnego środowiska zostało wykorzystane [uv](https://docs.astral.sh/uv/). W przypadku braku posiadania uv
należy je pobrać zgodnie z [dokumentacją](https://docs.astral.sh/uv/getting-started/installation/)

Aby utworzyć środowisko należy wpisać w terminalu
```bash
uv venv
```
Komenda ta zwróci komendę do aktywacji środowiska odpowiednią dla używanego OS

Aby zainstalować zależności należy wpisać
```bash
uv sync
```

### Uruchomienie programu

Najpierw należy uruchomić serwer proxy komendą
```bash
uv run python tcp_proxy.py
```
symulacje
```bash
uv run python tcp_simulator.py
```

oraz procedurę startu i lądowania
```bash
uv run python flight_sequences.py
```

Alternatywnie można wcześniej aktywować wirtualne środowisko komendą zwróconą przez `uv venv` i wtedy wpisać
```bash
python tcp_proxy.py
python tcp_simulation.py
python flight_sequences.py
```


