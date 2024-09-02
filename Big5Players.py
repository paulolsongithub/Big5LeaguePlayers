import requests
from bs4 import BeautifulSoup
import pandas as pd
from requests.exceptions import Timeout
import re
import time

leagues = {
    'Premier League': "https://en.wikipedia.org/wiki/2024%E2%80%9325_Premier_League",
    'Bundesliga': "https://en.wikipedia.org/wiki/2024%E2%80%9325_Bundesliga",
    'La Liga': "https://en.wikipedia.org/wiki/2024%E2%80%9325_La_Liga",
    'Serie A': "https://en.wikipedia.org/wiki/2024%E2%80%9325_Serie_A",
    'Ligue 1': "https://en.wikipedia.org/wiki/2024%E2%80%9325_Ligue_1"
}

def get_with_retry(url, retries=3, delay=5, timeout=10):
    for i in range(retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()  # Raise an HTTPError for bad responses
            return response
        except Timeout:
            print(f"Timeout occurred, retrying... ({i+1}/{retries})")
            time.sleep(delay)
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            break
    return None

def dms_to_decimal(dms_str):
    if not isinstance(dms_str, str):
        return None  # Return None if the input is not a string
    
    # Define regex to extract degrees, minutes, seconds, and direction
    dms_regex = re.compile(r'(\d+\.?\d*)°\s*(\d+\'?)?\s*(\d+\.?\d*)?"?\s*([NSEW])')
    
    matches = dms_regex.findall(dms_str)
    if not matches:
        return None
    
    decimal_degrees = 0.0
    
    for match in matches:
        degrees, minutes, seconds, direction = match
        degrees = float(degrees)
        minutes = float(minutes.replace("'", "")) if minutes else 0.0
        seconds = float(seconds) if seconds else 0.0
        
        decimal = degrees + (minutes / 60) + (seconds / 3600)
        
        # If direction is S or W, make it negative
        if direction in ['S', 'W']:
            decimal = -decimal
        
        decimal_degrees = decimal
    
    return decimal_degrees

def get_coordinates_from_city_page(city_link):
    """Helper function to extract and convert coordinates from a city page."""
    city_response = requests.get(city_link)
    city_soup = BeautifulSoup(city_response.content, 'html.parser')
    
    # Find the coordinates on the city page
    coordinates_tag = city_soup.find('span', {'class': 'geo-dec'}) or city_soup.find('span', {'class': 'geo'})
    if coordinates_tag:
        coordinates = coordinates_tag.get_text(strip=True)
        
        # Check if the coordinates are in DMS format
        if '°' in coordinates or '′' in coordinates or '″' in coordinates:
            lat_long = coordinates.split(" ")
            lat = dms_to_decimal(lat_long[0])
            long = dms_to_decimal(lat_long[1])
        else:
            lat, long = coordinates.split(",")
        
        return lat, long
    
    return None, None

all_players_data = []

for league_name, league_url in leagues.items():
    response = requests.get(league_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Select the correct table: 
    teams_table = soup.find_all('table', {'class': 'wikitable'})[0 if league_name == 'Premier League' else 1]
    
    teams = []

    for row in teams_table.find_all('tr')[1:]:
        cells = row.find_all('td')
        if len(cells) > 0:
            team_name = cells[0].get_text(strip=True)
            print(team_name)
            team_link = "https://en.wikipedia.org" + cells[0].find('a')['href']
            teams.append({'team_name': team_name, 'team_link': team_link})

    # Scrape each team's player data
    for team in teams:
        response = requests.get(team['team_link'])
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract team logo
        logo_tag = soup.find('td', class_='infobox-image')
        if logo_tag:
            img_tag = logo_tag.find('img')
            if img_tag:
                logo_url = "https:" + img_tag['src']
                team['logo_url'] = logo_url
                print(f"Team: {team['team_name']}, Logo URL: {team['logo_url']}")
            else:
                team['logo_url'] = None
        else:
            team['logo_url'] = None

        # Process the rest of the team data...
        squad_tables = soup.find_all('table', {'class': 'wikitable football-squad nogrid'})

        for table_index, table in enumerate(squad_tables):
            # Determine the label based on the table index
            if table_index == 0:
                squad_label = "First Team"
            else:
                squad_label = "On Loan"

            for row in table.find_all('tr')[1:]:
                player_cell = row.find('span', {'class': 'fn'})  # Find the player cell
                player_link_tag = player_cell.find('a') if player_cell else None
                if player_link_tag:
                    player_name = player_link_tag.get_text(strip=True)
                    player_link = "https://en.wikipedia.org" + player_link_tag['href']
                    players_data = {
                        'league': league_name,
                        'team': team['team_name'],
                        'team_logo': team['logo_url'],
                        'player_name': player_name,
                        'player_link': player_link,
                        'squad_status': squad_label,
                        'team_logo_url': team['logo_url']
                    }
                    all_players_data.append(players_data)
                    
totalplayers = len(all_players_data)
playerscompleted = 1

for player in all_players_data:
    response = get_with_retry(player['player_link'])
    
    if response is not None:
        soup = BeautifulSoup(response.content, 'html.parser')

        infobox = soup.find('table', {'class': 'infobox'})

        if infobox:
            rows = infobox.find_all('tr')

            for row in rows:
                header = row.find('th')
                if header:
                    header_text = header.get_text(strip=True)
                    if header_text == 'Place of birth':
                        player['place_of_birth'] = row.find('td').get_text(strip=True)
                        
                        # Extract the primary city link
                        city_link_tag = row.find('td').find('a', href=True)
                        
                        if city_link_tag:  # Check if city_link_tag is not None
                            city_link = "https://en.wikipedia.org" + city_link_tag['href']
                            
                            # Check if the primary link is a redlink (non-existent page)
                            if 'new' in city_link_tag.get('class', []):
                                # Look for a secondary link in the brackets
                                td_tag = row.find('td')
                                if td_tag:
                                    span_tag = td_tag.find('span', class_='noprint')
                                    if span_tag:
                                        secondary_link_tag = span_tag.find('a', class_='extiw')
                                        if secondary_link_tag:
                                            city_link = secondary_link_tag['href']
                            
                            # Navigate to the city page (either primary or secondary link) to find coordinates
                            lat, long = get_coordinates_from_city_page(city_link)
                            player['latitude'] = lat
                            player['longitude'] = long
                    elif header_text == 'Full name':
                        player['full_name'] = row.find('td').get_text(strip=True)
                    elif header_text == 'Date of birth':
                        player['date_of_birth'] = row.find('td').get_text(strip=True)
                    elif header_text == 'Height':
                        player['height'] = row.find('td').get_text(strip=True)
                    elif header_text == 'Position(s)':
                        player['position_full'] = row.find('td').get_text(strip=True)
                        
        print(f"{playerscompleted}/{totalplayers} Completed. {player['player_name']} playing at {player['team']}")
        playerscompleted += 1
        
    else:
        print(f"Failed to retrieve the page for {player['player_name']} at {player['player_link']}")
        
        playerscompleted += 1
              
# Convert the player data to a pandas DataFrame
df = pd.DataFrame(all_players_data)

# Save the DataFrame to a CSV file
df.to_csv('big_five_leagues_players.csv', index=False)

