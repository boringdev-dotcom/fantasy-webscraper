import requests
import json
from pprint import pprint

# Base URL for the API
BASE_URL = "http://localhost:8000"

def print_section(title):
    """Print a section title"""
    print("\n" + "=" * 50)
    print(f" {title} ".center(50, "="))
    print("=" * 50 + "\n")

def get_all_sports():
    """Get all available sports"""
    print_section("Getting All Sports")
    
    response = requests.get(f"{BASE_URL}/api/sports")
    sports = response.json()
    
    print(f"Found {len(sports)} sports:")
    for sport in sports:
        print(f"- {sport['name']} (ID: {sport['id']})")
    
    return sports

def get_nba_projections():
    """Get NBA projections"""
    print_section("Getting NBA Projections")
    
    # NBA ID is 7
    response = requests.get(f"{BASE_URL}/api/projections?sport_id=7")
    projections = response.json()
    
    print(f"Found {len(projections)} NBA projections")
    
    # Print first 5 projections
    for i, proj in enumerate(projections[:5]):
        print(f"\nProjection {i+1}:")
        print(f"  Player: {proj['player_name']}")
        print(f"  Stat Type: {proj['stat_type']}")
        print(f"  Line Score: {proj['line_score']}")
        if proj['start_time']:
            print(f"  Start Time: {proj['start_time']}")
    
    return projections

def search_player(player_name):
    """Search for a specific player"""
    print_section(f"Searching for Player: {player_name}")
    
    response = requests.get(f"{BASE_URL}/api/players/{player_name}")
    
    if response.status_code == 200:
        player = response.json()
        print(f"Found player: {player['name']}")
        print(f"Sport: {player['sport_name']}")
        print(f"Projections: {len(player['projections'])}")
        
        # Print player's projections
        if player['projections']:
            print("\nProjections:")
            for i, proj in enumerate(player['projections']):
                print(f"  {i+1}. {proj['stat_type']}: {proj['line_score']}")
        
        return player
    else:
        print(f"Player not found: {response.text}")
        return None

def get_sport_details(sport_id):
    """Get details for a specific sport"""
    print_section(f"Getting Details for Sport ID: {sport_id}")
    
    response = requests.get(f"{BASE_URL}/api/sports/{sport_id}")
    
    if response.status_code == 200:
        sport_data = response.json()
        print(f"Sport: {sport_data['sport']['name']}")
        print(f"Projections Count: {sport_data['projections_count']}")
        print(f"Games Count: {sport_data['games_count']}")
        print(f"Players Count: {sport_data['players_count']}")
        
        return sport_data
    else:
        print(f"Sport not found: {response.text}")
        return None

def main():
    """Main function to demonstrate API usage"""
    print("PrizePicks Fantasy Webscraper API Demo")
    
    # Get all sports
    sports = get_all_sports()
    
    # Get NBA projections
    nba_projections = get_nba_projections()
    
    # Search for a player (replace with a current player name)
    player = search_player("LeBron James")
    
    # Get details for NBA (ID: 7)
    sport_details = get_sport_details(7)
    
    print_section("Demo Complete")
    print("The API is working correctly!")

if __name__ == "__main__":
    main() 