import pandas as pd
import geopandas as gpd
import folium
import pyproj
from shapely import geometry
from shapely.geometry import Point
from openrouteservice import client
import logging
from dotenv import load_dotenv
import os
import re
import numpy as np

load_dotenv()

api_key = os.getenv('ORS_KEY')
ors = client.Client(key=api_key)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_coordinaten(x):
    """
    Parse de 'Omleiding via' string van het formaat '[lat, lon]' en retourneer een lijst van coördinaten [lat, lon].
    """
    if pd.isna(x) or str(x).strip() == '':
        return None
    try:
        x = str(x).strip()
        if x.startswith('[') and x.endswith(']'):
            x = x[1:-1]  # Remove brackets
            coords = [float(val.strip()) for val in x.split(',')]
            return coords
        return None
    except ValueError:
        return None
    
def load_data(wegen_afzettingen_path, werkdag_path, wegvakken_path, hectopunten_path):
    """
    Laad de gegevens voor de risicocategorieberekening.

    Argumenten:
    - wegen_afzettingen_path: Pad naar de CSV met afzetting locaties en details
    - werkdag_path: Pad naar de CSV met werkdaggegevens
    - wegvakken_path: Pad naar het shapefile met wegvakken
    - hectopunten_path: Pad naar het shapefile met hectopunten

    Returns:
    - wegen_afzettingen: DataFrame met afzetting locaties en details
    - werkdag_df: DataFrame met werkdaggegevens
    - nwb_gdf: GeoDataFrame met gecombineerde wegvak en hectometer informatie
    - wegvakken_gdf: GeoDataFrame met wegvakkengegevens (nodig voor junctie traversals bij bepalen normale route)
    """
    wegen_afzettingen = pd.read_csv(wegen_afzettingen_path, sep=';', converters={'Omleiding via': parse_coordinaten})
    werkdag_df = pd.read_csv(werkdag_path, sep=',', usecols=['vbn_oms_bp', 'wegnrhmp_b', 'bpszijde_b', 'hectoltr_b', 'hm_midden', 'al_e_wr'])

    wegvakken_gdf = gpd.read_file(wegvakken_path, columns=['WVK_ID', 'WEGNR_HMP', 'HECTO_LTTR', 'POS_TV_WOL', 'BEGINKM', 'EINDKM', 'JTE_ID_BEG', 'JTE_ID_END', 'geometry'])
    wegvakken_gdf = wegvakken_gdf[wegvakken_gdf['WEGNR_HMP'].str.match(r'^[AN]\d+$', na=False)].copy()
    wegvakken_gdf.to_crs(epsg=4326, inplace=True)
    hectopunten_gdf = gpd.read_file(hectopunten_path, columns=['WVK_ID','HECTOMTRNG', 'ZIJDE', 'HECTO_LTTR', ])
    hectopunten_gdf.to_crs(epsg=4326, inplace=True)

    nwb_gdf = wegvakken_gdf[['WVK_ID', 'WEGNR_HMP', 'HECTO_LTTR', 'POS_TV_WOL', 'BEGINKM', 'EINDKM']].merge(
        hectopunten_gdf[['WVK_ID', 'HECTOMTRNG', 'ZIJDE', 'geometry']],
        on='WVK_ID',
        how='inner')
    nwb_gdf = gpd.GeoDataFrame(nwb_gdf, geometry='geometry', crs='EPSG:4326')

    logger.info(f"Loaded {len(werkdag_df)} intensity records, {len(nwb_gdf)} geographic features")
    return wegen_afzettingen, werkdag_df, nwb_gdf, wegvakken_gdf

def parse_weg_data(input_weg:str):
    """
    Parse de wegdata string van het formaat 'A12 HMP 23.3 Re' of 'N50 HMP 45.6 Li Afrit 5' en extraheer de wegnummer, hectometer, zijde en afrit informatie.

    Arguementen:
    - input_weg: String met de wegdata van de afzetting locatie, zoals 'A12 HMP 23.3 Re' of 'N50 HMP 45.6 d'

    Returns:
    - data: Dictionary met informatie over de wegnummer, hectometer, zijde en afrit van de afzetting locatie. Indien parsing mislukt, wordt None geretourneerd.
    """
    try:
        pattern = r'^([AN]\d{1,3})\s+(?:HMP|KM)\s+([\d.]+)(?:\s+(Re|Li))?(?:\s+(.+))?$'
        match = re.match(pattern, input_weg.strip())
        
        if match:
            wegnummer = match.group(1)
            hectometer = float(match.group(2))
            zijde = match.group(3) if match.group(3) else ''
            afrit = match.group(4) if match.group(4) else ''
            
            # Als zijde = '' zoals bijv. bij 'A12 HMP 23.3 d'
            if zijde and len(zijde) == 1 and zijde not in ['Re', 'Li']:
                afrit = zijde
                zijde = ''
            
            logger.info(f"Parsed: wegnummer={wegnummer}, hectometer={hectometer}, zijde={zijde}, afrit={afrit}")
        else:
            logger.error(f"Could not parse input_weg: {input_weg}")
            return None
    except Exception as e:
        logger.error(f"Error parsing data: {e}")
        return None
    
    data = {"wegnummer": wegnummer, 
            "hectometer": hectometer, 
            "zijde": zijde, 
            "afrit": afrit}

    return data

def weg_data_naar_coordinaten(weg_data, hmp, nwb_gdf, hm_marge=1):
    """
    Zoekt naar de coördinaten van een afzetting op basis van de wegnummer, hectometer, zijde en afrit. Er wordt gezocht naar een match in het nwb_gdf GeoDataFrame binnen een bepaalde marge van hectometer.

    Arguementen:
    - weg_data: Dictionary met details van de afzetting (wegnummer, hectometer, zijde, afrit)
    - hmp: Hectometer van de afzetting
    - nwb_gdf: GeoDataFrame met wegvak en hectometer informatie
    - hm_marge: Marge in hectometer voor het zoeken naar een match in nwb_gdf. Standaard is 1 km.

    Returns:
    - coordinaten: [lat, lon] van de afzetting locatie. Indien geen match wordt gevonden, wordt None geretourneerd.
    """
    try:
        mask = (
            (nwb_gdf['WEGNR_HMP'] == weg_data['wegnummer']) &
            ((nwb_gdf['POS_TV_WOL'].eq(weg_data['zijde'][0]) | nwb_gdf['POS_TV_WOL'].isna()) if weg_data['zijde'] != '' else pd.Series(True, index=nwb_gdf.index)) &
            ((nwb_gdf['HECTO_LTTR'] == weg_data['afrit']) if weg_data['afrit'] else (nwb_gdf['HECTO_LTTR'] == '#')) &
            (nwb_gdf[['BEGINKM', 'EINDKM']].min(axis=1) - hm_marge <= hmp) &
            (hmp <= nwb_gdf[['BEGINKM', 'EINDKM']].max(axis=1) + hm_marge) &
            (abs((nwb_gdf['HECTOMTRNG'] / 10) - hmp) <= hm_marge) &
            ((nwb_gdf['ZIJDE'].eq(weg_data['zijde']) | nwb_gdf['ZIJDE'].isna()) if weg_data['zijde'] != '' else pd.Series(True, index=nwb_gdf.index)))
        matching = nwb_gdf[mask]
        
        match len(matching):
            case 0:
                logger.error(f"Geen matches gevonden voor {weg_data['wegnummer']} HMP {hmp} {weg_data['zijde']} {weg_data['afrit']}")
                return None
            case 1:
                logger.info(f"Exact één match gevonden voor {weg_data['wegnummer']} HMP {hmp} {weg_data['zijde']} {weg_data['afrit']}")
            case meerdere if len(matching) > 1:
                logger.warning(f"Meerdere gematchte records gevonden voor {weg_data['wegnummer']} HMP {hmp} {weg_data['zijde']} {weg_data['afrit']}, sorteren en dichtstbijzijnde kiezen...")
                matching_sort = matching.copy()
                matching_sort['dist_to_hmp'] = matching_sort.apply(
                lambda row: min(
                    abs(row['BEGINKM'] - hmp) if pd.notna(row['BEGINKM']) else float('inf'),
                    abs(row['EINDKM'] - hmp) if pd.notna(row['EINDKM']) else float('inf')),axis=1)
                matching = matching_sort.sort_values('dist_to_hmp')
            case _:
                logger.error(f"Onverwachte waarde voor len(matching) bij zoeken naar coordinaten")
                return None

        best_match = matching.iloc[0]

        weg_data['wegvak_id'] = best_match['WVK_ID']
    
        if weg_data['zijde'] == '' and pd.notna(best_match['POS_TV_WOL']):
            weg_data['zijde'] = 'Re' if best_match['POS_TV_WOL'] == 'R' else 'Li' if best_match['POS_TV_WOL'] == 'L' else ''
            logger.info(f"Zijde afgeleid van POS_TV_WOL '{best_match['POS_TV_WOL']}': {weg_data['zijde']}")
    
    
        coordinaten = [best_match.geometry.y, best_match.geometry.x]
        return coordinaten
        
    except Exception as e:
        logger.error(f"Error retrieving coordinates: {e}")
        return None

def calculate_intensiteit(afzetting_data, werkdag_df, hm_marge=1):
    """
    Berekenen van de gemiddelde dagelijkse intensiteit op basis van de wegnummer, hectometer, zijde en afrit van de afzetting. Er wordt gezocht naar een match in het werkdag_df dataframe binnen een bepaalde marge van hectometer. 
    Indien meerdere matches worden gevonden, wordt de match met de dichtstbijzijnde hectometer gekozen.

    Arguementen:
    - afzetting_data: Dictionary met details van de afzetting (wegnummer, hectometer, zijde, afrit)
    - werkdag_df: DataFrame met intensiteit gegevens per wegvak.
    - hm_marge: Marge in hectometer voor het zoeken naar een match in werkdag_df. Standaard is 1 km.

    Returns:
    - intensiteit: Gemiddelde dagelijkse intensiteit op de wegvak nabij de afzetting. Indien geen match wordt gevonden, wordt None geretourneerd.
    """
    try:
        mask = (
            (werkdag_df['wegnrhmp_b'] == afzetting_data['wegnummer']) &
            (abs(werkdag_df['hm_midden'] - afzetting_data['hectometer']) <= hm_marge) &
            ((werkdag_df['bpszijde_b'].eq(afzetting_data['zijde']) | werkdag_df['bpszijde_b'].isna()) if afzetting_data['zijde'] != '' else pd.Series(True, index=werkdag_df.index)) &
            (werkdag_df['hectoltr_b'].isna() | (werkdag_df['hectoltr_b'].eq(afzetting_data['afrit']) if afzetting_data['afrit'] else pd.Series(False, index=werkdag_df.index))))
        
        matching_rows = werkdag_df[mask]
        
        if len(matching_rows) == 0:
            logger.warning(f"Geen gematchte rij in werkdag_df gevonden voor: {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} {afzetting_data['zijde']} {afzetting_data['afrit']}")
            return None
        elif len(matching_rows) > 1:
            matching_rows = matching_rows.copy()
            matching_rows['hm_diff'] = abs(matching_rows['hm_midden'] - afzetting_data['hectometer'])
            matching_rows = matching_rows.sort_values('hm_diff')
            logger.warning(f"Meerdere gematchte rijen gevonden in werkdag_df voor: {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} {afzetting_data['zijde']} {afzetting_data['afrit']}. Returning closest hectometer match.")
        
        intensiteit = matching_rows.iloc[0]['al_e_wr']
        logger.info(f"Intensiteit gevonden: {intensiteit} voor {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} {afzetting_data['zijde']} {afzetting_data['afrit']}")
        
        return intensiteit
    
    except Exception as e:
        logger.error(f"Error bij berekenen intensiteit: {e}")
        return None

def vind_coordinaat_via_junctie(wegvak_id, richting, wegvakken_gdf, stappen=5):
    """
    Traverse the road graph from wegvak_id to find a coordinate
    'stappen' wegvakken upstream (richting='voor') or downstream (richting='na').
    Returns the midpoint geometry of the found wegvak.
    If a dead-end is encountered, returns the coordinate of the last valid segment.
    """
    huidig_wegvak = wegvakken_gdf[wegvakken_gdf['WVK_ID'] == wegvak_id]
    if huidig_wegvak.empty:
        return None

    for i in range(stappen):
        if richting == 'voor': # Find wegvakken whose END junction matches our BEGIN junction
            zoek_junctie = huidig_wegvak.iloc[0]['JTE_ID_BEG']
            kandidaten = wegvakken_gdf[wegvakken_gdf['JTE_ID_END'] == zoek_junctie]
        elif richting == 'na': # Find wegvakken whose BEGIN junction matches our END junction  
            zoek_junctie = huidig_wegvak.iloc[0]['JTE_ID_END']
            kandidaten = wegvakken_gdf[wegvakken_gdf['JTE_ID_BEG'] == zoek_junctie]

        kandidaten = kandidaten[kandidaten['WVK_ID'] != huidig_wegvak.iloc[0]['WVK_ID']]
        match len(kandidaten):
            case 0:
                logger.warning(f"Geen aangrenzend wegvak gevonden bij junctie {zoek_junctie}. Teruggeven huidge locatie na {i} stappen.")
                break  # Break out of loop and return current wegvak's coordinate
            case multiple if len(kandidaten) > 1:
                logger.warning(f"Meerdere aangrenzende wegvakken gevonden bij junctie {zoek_junctie}, prefereren wegvak op dezelfde wegnummer...")
                zelfde_weg = kandidaten[kandidaten['WEGNR_HMP'] == huidig_wegvak.iloc[0]['WEGNR_HMP']]
                huidig_wegvak = zelfde_weg.iloc[[0]] if not zelfde_weg.empty else kandidaten.iloc[[0]]
            case 1:
                huidig_wegvak = kandidaten.iloc[[0]] 
            case _:
                logger.error(f"Onverwachte waarde voor len(kandidaten)")
                return None

    geom = huidig_wegvak.iloc[0].geometry.interpolate(0.5, normalized=True)
    mid = [geom.y, geom.x]  # Return middelpunt als [lat, lon]
    return mid

def calculate_normale_rit_data(afzetting_data, wegvakken_gdf):
    """
    Berekenen van de begin- en eindcoördinaten van de route op basis van de afzetting locatie en wegvak informatie.

    Argumenten:
    - afzetting_data: Dictionary met details van de afzetting (wegnummer, hectometer, zijde, afrit)
    - wegvakken_gdf: GeoDataFrame met wegvak informatie.

    Returns:
    - normale_rit_data: Dictionary met 'begin' en 'eind' coördinaten van de normale route.
    """
    normale_rit_data = afzetting_data.copy()
    wegvak_id = afzetting_data.get('wegvak_id')

    if not wegvak_id:
        logger.error(f"Geen wegvak_id beschikbaar voor {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']}, normale rit data kan niet bepaald worden")
        return None

    if normale_rit_data['zijde'] == 'Li': # HM-Palen zijn aflopend in nummer bij zijde Links, hierbij moet dus het begin na de junctie zijn en het eind voor
        normale_rit_data['begin'] = vind_coordinaat_via_junctie(wegvak_id, 'na',   wegvakken_gdf)
        normale_rit_data['eind']  = vind_coordinaat_via_junctie(wegvak_id, 'voor', wegvakken_gdf)
    elif normale_rit_data['zijde'] == 'Re':  #  HM-Palen zijn oplopend in nummer bij zijde Rechts, hierbij moet dus het begin voor de junctie zijn en het eind na
        normale_rit_data['begin'] = vind_coordinaat_via_junctie(wegvak_id, 'voor', wegvakken_gdf)
        normale_rit_data['eind']  = vind_coordinaat_via_junctie(wegvak_id, 'na',   wegvakken_gdf)
    else:
        logger.error(f"Zijde is onbekend voor {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']}, normale rit data kan niet bepaald worden")
        return None

    if normale_rit_data['begin'] is None or normale_rit_data['eind'] is None:
        logger.error(f"Geen geldige coördinaten voor normale route bij {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']}")
        return None

    return normale_rit_data

def calculate_normale_route(normale_rit_data):
    """
    Bepaal de normale route via de ORS API op basis van de begin- en eindcoördinaten. Deze route dient als referentie voor de reistijd zonder afzetting.

    Argumenten:
    - normale_rit_data: Dictionary met 'begin' en 'eind' coördinaten van de normale route

    Returns:
    - route_normaal: GeoJSON data van de normale route, inclusief reistijd en afstand. Deze data wordt later gebruikt voor vergelijking met de omleidingsroute.
    """
    request_params = {'coordinates': [list(reversed(normale_rit_data['begin'])), list(reversed(normale_rit_data['eind']))], # Reversed omdat ORS API [lon, lat] verwacht
                          'format_out': 'geojson',
                          'profile': 'driving-car',
                          'preference': 'fastest',
                          'instructions': 'false'}
    try:
        route_normaal = ors.directions(**request_params)
    except Exception as e:
        logger.error(f"Error fetching normale route from API: {e}")
        return None

    return route_normaal

def maak_buffer_polygon(coordinaten, resolution=10, radius=10, for_api=False): # Radius in meter, for_api nodig voor juiste volgorde van coordinaten x, y of y, x
    """
    Maakt een bufferpolygon rond een gegeven coördinaat. Gevonden op https://openrouteservice.org/example-avoid-obstacles-while-routing/.

    Argumenten:
    - coordinaten: [lat, lon] in EPSG:4326
    - resolution: Resolutie van het bufferpolygon
    - radius: Straal van de buffer in meter
    - for_api: Indien True, worden de coordinaten geretourneerd in de volgorde [lon, lat] voor gebruik in de ORS API

    Returns:
    - poly_wgs: Lijst van coördinaten van het bufferpolygon
    """
    point_in = coordinaten # [lat, lon] in EPSG:4326
    convert = pyproj.Transformer.from_crs("epsg:4326", 'epsg:32632')
    convert_back = pyproj.Transformer.from_crs('epsg:32632', "epsg:4326")
    point_in_proj = convert.transform(*point_in) # [lat, lon] (WGS_y, WGS_x) -> [x, y] in EPSG:32632
    point_buffer_proj = Point(point_in_proj).buffer(radius, resolution=resolution)

    poly_wgs = []
    for point in point_buffer_proj.exterior.coords:
        transformed = convert_back.transform(*point) # [x, y] -> [lat, lon] (WGS_y, WGS_x) in EPSG:4326
        if for_api:
            poly_wgs.append([transformed[1], transformed[0]])  # [lon, lat] voor ORS API
        else:
            poly_wgs.append([transformed[0], transformed[1]])  # [lat, lon] voor folium
    
    return poly_wgs

def calculate_omleiding_route(normale_rit_data, afzetting_data, omleiding_via=None):
    """
    Bepaal de omleidingsroute via de ORS API. Als er een expliciete omleiding_via coördinaat is opgegeven, gebruik deze dan als tussenpunt.

    Argumenten:
    - normale_rit_data: Dictionary met 'begin' en 'eind' coördinaten van de normale route
    - afzetting_data: Dictionary met details van de afzetting (wegnummer, hectometer, zijde, afrit)
    - omleiding_via: Optioneel [lat, lon] coördinaat dat als tussenpunt moet worden gebruikt voor de omleidingsroute. Als None, bereken dan een route die een bufferzone rond de afzetting vermijdt.
    
    Returns:
    - route_omleiding: GeoJSON data van de omleidingsroute, inclusief reistijd en afstand. Deze data wordt later gebruikt voor vergelijking met de normale route.
    """
    if omleiding_via:
        request_params = {'coordinates': [list(reversed(normale_rit_data['begin'])), list(reversed(omleiding_via)), list(reversed(normale_rit_data['eind']))], # Reversed omdat ORS API [lon, lat] verwacht
                          'format_out': 'geojson',
                          'profile': 'driving-car',
                          'preference': 'fastest',
                          'instructions': 'false'}
        try:
            route_omleiding = ors.directions(**request_params)
        except Exception as e:
            logger.error(f"Error fetching omleiding route from API: {e}")
            return None
        
    else:
        logger.warning(f"Afzetting {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} heeft geen gedefinieerde omleidingsroute, berekenen via vermijding van bufferzone...")
        buffer_polygon_coords = maak_buffer_polygon(afzetting_data['coordinaten'], for_api=True)  # Buffer polygon in [lon, lat]
        buffer_polygon = geometry.Polygon(buffer_polygon_coords) 
        request_params = {'coordinates': [list(reversed(normale_rit_data['begin'])), list(reversed(normale_rit_data['eind']))],
                          'format_out': 'geojson',
                          'profile': 'driving-car',
                          'preference': 'fastest',
                          'instructions': 'false',
                          'options':{'avoid_polygons': geometry.mapping(buffer_polygon)}} 
        try:
            route_omleiding = ors.directions(**request_params)
        except Exception as e:
            logger.error(f"Error fetching omleiding route from API: {e}")
            return None
        
    return route_omleiding

def calculate_risico_categorie(afzetting_data, intensiteit, route_normaal, route_omleiding):
    """
    Bepaal de risico categorie op basis van de intensiteit en het verschil in reistijd tussen de normale route en de omleidingsroute.

    Argumenten:
    - afzetting_data: Dictionary met details van de afzetting (wegnummer, hectometer, zijde, afrit)
    - intensiteit: Gemiddelde dagelijkse intensiteit op de wegvak nabij de afzetting
    - route_normaal: GeoJSON data van de normale route (zonder afzetting)
    - route_omleiding: GeoJSON data van de omleidingsroute (met afzetting of vermijding bufferzone)

    Returns:
    - risico_categorie: Categorie van het risico (A, B, C, D, E) op basis van de matrix van hinderklasse en intensiteit.
    """
    if not intensiteit or not route_normaal or not route_omleiding:
        logger.warning("Data voor berekenen van risico categorie is incompleet")
        return None
    
    try:
        delay_minutes = (route_omleiding['features'][0]['properties']['summary']['duration'] -
                        route_normaal['features'][0]['properties']['summary']['duration']) / 60
        
        # Searchsorted geeft index terug waar waarde in lijst past, dus als delay_minutes=7 dan past die in [5,10,30] op index 1 (tussen 5 en 10). Voor hinderklasse moet dan +1 gedaan worden.
        hinderklasse = int(np.searchsorted([5, 10, 30], delay_minutes) + 1)
        intensiteit_index = int(np.searchsorted([1000, 10000, 100000], intensiteit))
        
        risico_matrix = {
            1: ['E', 'D', 'C', 'B'],
            2: ['D', 'C', 'C', 'B'],
            3: ['C', 'B', 'A', 'A'],
            4: ['C', 'B', 'A', 'A']}

        risico_categorie = risico_matrix[hinderklasse][intensiteit_index]
        logger.info(f"Risico categorie berekend: {risico_categorie} voor {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} {afzetting_data['zijde']} {afzetting_data['afrit']}")

        return risico_categorie
    
    except Exception as e:
        logger.error(f"Error bij berekening risico categorie: {e}")
        return None

def visualize_routes(afzetting_data, route_normaal, route_omleiding):
    """
    Visualiseer de normale route, omleidingsroute, afzetting locatie en bufferzone op een interactieve kaart met folium.

    Argumenten:
    - afzetting_data: Dictionary met details van de afzetting (wegnummer, hectometer, zijde, afrit, coordinaten)
    - route_normaal: GeoJSON data van de normale route (zonder afzetting)
    - route_omleiding: GeoJSON data van de omleidingsroute (met afzetting of vermijding bufferzone)

    Returns:
    - Een opgeslagen HTML-bestand met de interactieve kaart visualisatie. Deze wordt opgeslagen in de 'Output' map met een naam gebaseerd op de afzetting details.
    """
    map1 = folium.Map(location=afzetting_data['coordinaten'], zoom_start=12)
    folium.features.GeoJson(data=route_normaal, name= 'Normale route (zonder afzetting)', style_function=lambda x: {'color':"#15FF00", 'weight':5, 'opacity':0.9}, overlay=True).add_to(map1)
    folium.features.GeoJson(data=route_omleiding, name= 'Omleidings route (met afzetting)', style_function=lambda x: {'color':"#FF9900", 'weight':5, 'opacity':0.9}, overlay=True).add_to(map1)
    folium.features.Marker(location=afzetting_data['coordinaten'], popup=f"Afzetting locatie: {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} {afzetting_data['zijde']} {afzetting_data['afrit']}", icon=folium.Icon(color='red', icon='info-sign')).add_to(map1)
    folium.vector_layers.Polygon(locations=maak_buffer_polygon(afzetting_data['coordinaten'], resolution=10, radius=10), color="#FF6767", fill=True, fill_opacity=0.2, popup='Afzetting buffer zone (5m)').add_to(map1) if afzetting_data.get('Omleiding via') is None else None

    map1_titel = f"Kaart Routes Afzetting {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} {afzetting_data['zijde']} {afzetting_data['afrit']}"
    map1.get_root().html.add_child(folium.Element(map1_titel))
    map1.save(f'Output/{map1_titel}.html')

def main_risico_categorie_berekening():
    wegen_afzettingen, werkdag_df, nwb_gdf, wegvakken_gdf = load_data('wegen_afzettingen.csv', 'Static Inputs/werkdag_gemiddelde_intensiteiten_in_2024_h.csv', 'Static Inputs/Wegvakken.gpkg', 'Static Inputs/Hectopunten.gpkg')
    appended_data = []

    for idx, weg_data in wegen_afzettingen.iterrows():
        try:
            afzetting_data = weg_data.to_dict()
            afzetting_data.update(parse_weg_data(weg_data['Afzetting locatie']))
            afzetting_data['coordinaten'] = weg_data_naar_coordinaten(afzetting_data, afzetting_data['hectometer'], nwb_gdf)
            intensiteit = calculate_intensiteit(afzetting_data, werkdag_df)
            normale_rit_data = calculate_normale_rit_data(afzetting_data, wegvakken_gdf)
            route_normaal = calculate_normale_route(normale_rit_data)
            route_omleiding = calculate_omleiding_route(normale_rit_data, afzetting_data, omleiding_via=afzetting_data.get('Omleiding via'))
            risico_categorie = calculate_risico_categorie(afzetting_data, intensiteit, route_normaal, route_omleiding)

            afzetting_data.update({
                'intensiteit': intensiteit,
                'normale_reistijd':   route_normaal['features'][0]['properties']['summary']['duration'],
                'omleiding_reistijd': route_omleiding['features'][0]['properties']['summary']['duration'],
                'risico_categorie': risico_categorie})
            appended_data.append(pd.DataFrame([afzetting_data]))

            visualize_routes(afzetting_data, route_normaal, route_omleiding)
        except Exception as e:
            logger.error(f"Error processing row {idx} for {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} {afzetting_data.get('zijde')} {afzetting_data.get('afrit')}: {e}")
            continue

    risicoberekening_output = pd.DataFrame(pd.concat(appended_data))
    risicoberekening_output.to_csv('Output/Risicoberekening NO11 - Geautomatiseerd.csv')

if __name__ == "__main__":
    main_risico_categorie_berekening()