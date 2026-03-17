# Traffic Risicocategorieën Automatisering

Automatisering van risicocategorieberekeningen voor verkeersafzettingen op Nederlandse wegen.

## Beschrijving

Dit project berekent automatisch de risicocategorie voor verkeersstremming veroorzaakt door wegafzettingen. Het bepaalt:
- De normale route en reistijd zonder afzetting
- De omleidingsroute en reistijd met afzetting
- De intensiteit op de betrokken wegvakken
- De risicocategorie (A-E) op basis van reisvertraging en verkeersintensiteit

## Functionaliteiten

- **Coördinaatbepaling**: Converteert weginformatie (weg, hectometer, zijde) naar geografische coördinaten
- **Intensiteitsberekening**: Haalt werkdagintensiteiten op uit historische gegevens
- **Routeberekening**: Gebruikt OpenRouteService (ORS) API voor normale en omleidingsroutes
- **Risicoanalyse**: Bepaalt risicocategorie op basis van reisvertraging en intensiteit
- **Visualisatie**: Genereert interactieve kaarten (HTML) voor elke afzetting

## Vereisten

- Python 3.10+
- Packages: `pandas`, `geopandas`, `folium`, `pyproj`, `shapely`, `openrouteservice`, `python-dotenv`
- API-Keys: https://openrouteservice.org/

## Installatie

```bash
pip install pandas geopandas folium pyproj shapely openrouteservice python-dotenv
```

## Setup
1. OpenRouteService API-sleutel:
    - Registreer op https://openrouteservice.org/
    - Maak een .env bestand in de projectmap:
2. Input-bestanden: Plaats de volgende bestanden in Static Inputs/:
    - Wegvakken.gpkg — Wegvakkengegevens
    - Hectopunten.gpkg — Hectometerpunten
    - werkdag_gemiddelde_intensiteiten_in_2024_h.csv — Intensiteitsgegevens
3. CSV met afzettingen: wegen_afzettingen.csv in de projectmap met kolommen:
    - Afzetting locatie — Bijv. "A12 HMP 23.3 Re" of "N50 HMP 45.6 Li Afrit 5"
    - Omleiding via (optioneel) — Coördinaten als [lat, lon]

## Gebruik
```bash
py -m risico_categorie_berekenen.py
py -m streamlit run risico_app.py
```

Output:
- Output/Risicoberekening NO11 - Geautomatiseerd.csv — Resultaten per afzetting
- Output/Kaart Routes Afzetting [details].html — Interactieve kaarten

## Structuur
```
├── risico_categorie_berekenen.py    # Hoofdscript
├── risico_app.py                    # (aanvullende applicatie)
├── wegen_afzettingen.csv            # Input-data
├── .env                             # API-sleutel (niet gecommit)
├── .gitignore
├── README.md
├── Static Inputs/
│   ├── Wegvakken.gpkg
│   ├── Hectopunten.gpkg
│   └── werkdag_gemiddelde_intensiteiten_in_2024_h.csv
└── Output/
    ├── Risicoberekening NO11 - Geautomatiseerd.csv
    └── Kaart Routes Afzetting [details].html
```

## Logica Risicocategorieberekening
De risicocategorie wordt conform de CROW bepaald aan de hand van:

1. Hinderklasse (op basis van reisvertraging):
    - Klasse 1: < 5 minuten
    - Klasse 2: 5-10 minuten
    - Klasse 3: 10-30 minuten
    - Klasse 4: > 30 minuten
2. Intensiteitsindex (op basis van gemiddelde dagintensiteit):
    - Index 0: < 1.000 voertuigen/dag
    - Index 1: 1.000-10.000 voertuigen/dag
    - Index 2: 10.000-100.000 voertuigen/dag
    - Index 3: > 100.000 voertuigen/dag

## Opmerking
Dit project maakt gebruik van Nederlandse weggegevens (NWB) en hectometerpunten. De API-sleutel moet veilig worden beheerd en nooit in versiebeheer worden opgenomen.