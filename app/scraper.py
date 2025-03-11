import sys
import requests
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import random
import uuid
from app.models import Sport, Player, Game, Projection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class PrizePicksScraper:
    """
    A scraper for the PrizePicks API to fetch sports, players, games, and projections data.
    """
    
    BASE_URL = "https://api.prizepicks.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://app.prizepicks.com/",
        "X-Device-ID": "1a9d6304-65f3-4304-8523-ccf458d3c0c4",  # This will be replaced in __init__
        "sec-ch-ua": "\"Not/A)Brand\";v=\"8\", \"Chromium\";v=\"126\", \"Google Chrome\";v=\"126\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"macOS\""
    }
    
    # Cache to store data and reduce API calls
    _sports_cache = None
    _sports_cache_time = 0
    _projections_cache = {}
    _projections_cache_time = {}
    _players_cache = {}
    _games_cache = {}
    
    # Cache expiration time in seconds (15 minutes)
    CACHE_EXPIRY = 15 * 60
    
    @staticmethod
    def _generate_device_id() -> str:
        """Generate a random device ID in UUID format."""
        return str(uuid.uuid4())
    
    def __init__(self):
        """Initialize the scraper with default settings."""
        self.session = requests.Session()
        
        # Create a copy of the headers and update with a random device ID
        headers = self.HEADERS.copy()
        headers["X-Device-ID"] = self._generate_device_id()
        
        self.session.headers.update(headers)
        logger.info("Initialized PrizePicksScraper with new device ID")
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a request to the PrizePicks API.
        
        Args:
            endpoint: The API endpoint to request
            params: Optional query parameters
            
        Returns:
            The JSON response as a dictionary
        """
        url = f"{self.BASE_URL}/{endpoint}"
        
        # Maximum number of retries
        max_retries = 3
        retry_count = 0
        backoff_factor = 1.5
        
        while retry_count < max_retries:
            try:
                # Add a small random delay to avoid rate limiting
                time.sleep(random.uniform(0.5, 1.0))
                
                logger.info(f"Making request to {url} with params {params}")
                logger.debug(f"Request headers: {self.session.headers}")
                
                response = self.session.get(url, params=params)
                
                # Log response details
                logger.info(f"Response status: {response.status_code}")
                logger.debug(f"Response headers: {response.headers}")
                
                if response.status_code != 200:
                    logger.warning(f"Non-200 response: {response.text[:500]}")
                
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"API request failed after {max_retries} attempts: {e}")
                    raise Exception(f"Failed to fetch data from PrizePicks API: {str(e)}")
                
                # Calculate backoff time with jitter
                backoff_time = (backoff_factor ** retry_count) + random.uniform(0.1, 0.5)
                logger.warning(f"Request failed, retrying in {backoff_time:.2f} seconds... (Attempt {retry_count}/{max_retries})")
                time.sleep(backoff_time)
    
    def get_sports(self) -> List[Sport]:
        """
        Get all available sports from PrizePicks.
        
        Returns:
            A list of Sport objects
        """
        # Check if cache is valid
        current_time = time.time()
        if self._sports_cache and (current_time - self._sports_cache_time) < self.CACHE_EXPIRY:
            return self._sports_cache
        
        # Fetch sports data
        response = self._make_request("leagues")
        
        sports = []
        if "data" in response:
            for sport_data in response["data"]:
                try:
                    sport = Sport(
                        id=int(sport_data["id"]),
                        name=sport_data["attributes"]["name"],
                        category=sport_data["attributes"].get("category"),
                        active=sport_data["attributes"].get("active", True)
                    )
                    sports.append(sport)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse sport data: {e}")
        
        # Update cache
        self._sports_cache = sports
        self._sports_cache_time = current_time
        
        return sports
    
    def get_sport_data(self, sport_id: int) -> Dict[str, Any]:
        """
        Get detailed data for a specific sport.
        
        Args:
            sport_id: The ID of the sport
            
        Returns:
            A dictionary with sport data
        """
        # First check if we have this sport in our cache
        sports = self.get_sports()
        sport = next((s for s in sports if s.id == sport_id), None)
        
        if not sport:
            raise Exception(f"Sport with ID {sport_id} not found")
        
        # Get projections for this sport
        projections = self.get_projections(sport_id=sport_id)
        
        # Get games for this sport
        games = self.get_games(sport_id=sport_id)
        
        # Get players for this sport
        players = self.get_players(sport_id=sport_id)
        
        return {
            "sport": sport.dict(),
            "projections_count": len(projections),
            "games_count": len(games),
            "players_count": len(players),
            "projections": [p.dict() for p in projections[:10]],  # Return only first 10 projections
            "games": [g.dict() for g in games[:10]],  # Return only first 10 games
            "players": [p.dict() for p in players[:10]]  # Return only first 10 players
        }
    
    def get_projections(
        self, 
        sport_id: Optional[int] = None, 
        player_name: Optional[str] = None,
        stat_type: Optional[str] = None
    ) -> List[Projection]:
        """
        Get projections from PrizePicks, with optional filters.
        
        Args:
            sport_id: Optional filter by sport ID
            player_name: Optional filter by player name
            stat_type: Optional filter by stat type
            
        Returns:
            A list of Projection objects
        """
        # Create cache key based on parameters
        cache_key = f"projections_{sport_id}_{player_name}_{stat_type}"
        
        # Check if cache is valid
        current_time = time.time()
        if (
            cache_key in self._projections_cache and 
            (current_time - self._projections_cache_time.get(cache_key, 0)) < self.CACHE_EXPIRY
        ):
            logger.info(f"Returning cached projections for {cache_key}")
            return self._projections_cache[cache_key]
        
        logger.info(f"Cache Miss: Fetching projections for {cache_key}")

        # Prepare query parameters
        params = {
            "single_stat": True,
            "game_mode": "pickem"
        }
        
        # For league_id 7 (which appears to be NFL based on the curl command), 
        # we can request more projections per page
        if sport_id == 7:
            params["per_page"] = 250
        else:
            params["per_page"] = 50  # Default for other leagues
        
        if sport_id:
            params["league_id"] = sport_id
        
        # Fetch projections data
        response = self._make_request("projections", params)
        
        projections = []
        if "data" in response and "included" in response:
            # Create lookup dictionaries for included data
            players_dict = {}
            leagues_dict = {}
            games_dict = {}
            
            for included in response["included"]:
                if included["type"] == "new_player":
                    players_dict[included["id"]] = included
                elif included["type"] == "league":
                    leagues_dict[included["id"]] = included
                elif included["type"] == "game":
                    games_dict[included["id"]] = included
            
            # Process projection data
            for proj_data in response["data"]:
                try:
                    # Get related data
                    player_id = proj_data["relationships"]["new_player"]["data"]["id"]
                    player_data = players_dict.get(player_id, {})
                    
                    league_id = proj_data["relationships"]["league"]["data"]["id"]
                    league_data = leagues_dict.get(league_id, {})
                    
                    game_id = None
                    game_data = {}
                    if "game" in proj_data["relationships"] and proj_data["relationships"]["game"]["data"]:
                        game_id = proj_data["relationships"]["game"]["data"]["id"]
                        game_data = games_dict.get(game_id, {})
                    
                    # Extract player name
                    player_name_value = player_data.get("attributes", {}).get("name", "Unknown Player")
                    
                    # Skip if player_name filter is provided and doesn't match
                    if player_name and player_name.lower() not in player_name_value.lower():
                        continue
                    
                    # Extract stat type
                    stat_type_value = proj_data["attributes"].get("stat_type", "Unknown")
                    
                    # Skip if stat_type filter is provided and doesn't match
                    if stat_type and stat_type.lower() != stat_type_value.lower():
                        continue
                    
                    # Parse start time if available
                    start_time = None
                    if "start_time" in proj_data["attributes"] and proj_data["attributes"]["start_time"]:
                        try:
                            start_time = datetime.fromisoformat(proj_data["attributes"]["start_time"].replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            pass
                    
                    # Create projection object
                    projection = Projection(
                        id=proj_data["id"],
                        player_id=player_id,
                        player_name=player_name_value,
                        sport_id=int(league_id),
                        sport_name=league_data.get("attributes", {}).get("name", "Unknown"),
                        game_id=game_id,
                        stat_type=stat_type_value,
                        line_score=float(proj_data["attributes"].get("line_score", 0)),
                        description=proj_data["attributes"].get("description"),
                        start_time=start_time,
                        is_active=proj_data["attributes"].get("is_active", True),
                        opponent=game_data.get("attributes", {}).get("away_team")
                    )
                    if len(projections) > 30:
                        break
                    projections.append(projection)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse projection data: {e}")
        
        # Update cache
        self._projections_cache[cache_key] = projections
        self._projections_cache_time[cache_key] = current_time
        
        return projections
    
    def get_players(self, sport_id: Optional[int] = None) -> List[Player]:
        """
        Get players from PrizePicks, optionally filtered by sport.
        
        Args:
            sport_id: Optional filter by sport ID
            
        Returns:
            A list of Player objects
        """
        # Create cache key
        cache_key = f"players_{sport_id}"
        
        # Check if cache is valid
        if cache_key in self._players_cache:
            return self._players_cache[cache_key]
        
        # Get projections which contain player data
        projections = self.get_projections(sport_id=sport_id)
        
        # Extract unique players from projections
        players_dict = {}
        for proj in projections:
            if proj.player_id not in players_dict:
                # Create a new player
                player = Player(
                    id=proj.player_id,
                    name=proj.player_name,
                    sport_id=proj.sport_id,
                    sport_name=proj.sport_name,
                    projections=[proj.dict()]
                )
                players_dict[proj.player_id] = player
            else:
                # Add projection to existing player
                players_dict[proj.player_id].projections.append(proj.dict())
        
        players = list(players_dict.values())
        
        # Update cache
        self._players_cache[cache_key] = players
        
        return players
    
    def get_player_by_name(self, player_name: str) -> Optional[Player]:
        """
        Get a player by name.
        
        Args:
            player_name: The name of the player to find
            
        Returns:
            A Player object if found, None otherwise
        """
        # Get all players
        all_players = self.get_players()
        
        # Find player by name (case-insensitive partial match)
        for player in all_players:
            if player_name.lower() in player.name.lower():
                return player
        
        return None
    
    def get_games(self, sport_id: Optional[int] = None) -> List[Game]:
        """
        Get games from PrizePicks, optionally filtered by sport.
        
        Args:
            sport_id: Optional filter by sport ID
            
        Returns:
            A list of Game objects
        """
        # Create cache key
        cache_key = f"games_{sport_id}"
        
        # Check if cache is valid
        if cache_key in self._games_cache:
            return self._games_cache[cache_key]
        
        # Get projections which contain game data
        projections = self.get_projections(sport_id=sport_id)
        
        # Extract unique games from projections
        games_dict = {}
        for proj in projections:
            if not proj.game_id:
                continue
                
            if proj.game_id not in games_dict:
                # Create a new game (with limited information)
                game = Game(
                    id=proj.game_id,
                    sport_id=proj.sport_id,
                    sport_name=proj.sport_name,
                    home_team="Unknown",  # We don't have this info from projections
                    away_team=proj.opponent or "Unknown",
                    start_time=proj.start_time,
                    players=[proj.player_id]
                )
                games_dict[proj.game_id] = game
            else:
                # Add player to existing game
                if proj.player_id not in games_dict[proj.game_id].players:
                    games_dict[proj.game_id].players.append(proj.player_id)
        
        games = list(games_dict.values())
        
        # Update cache
        self._games_cache[cache_key] = games
        
        return games
    
    def get_game_by_id(self, game_id: str) -> Optional[Game]:
        """
        Get a game by ID.
        
        Args:
            game_id: The ID of the game to find
            
        Returns:
            A Game object if found, None otherwise
        """
        # Get all games
        all_games = self.get_games()
        
        # Find game by ID
        for game in all_games:
            if game.id == game_id:
                return game
        
        return None 