import requests
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import random
import uuid
from app.models import Sport, Player, Game, Projection
import threading
from collections import deque
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RateLimiter:
    """Rate limiter using token bucket algorithm"""
    def __init__(self, rate: float, burst: int):
        self.rate = rate  # requests per second
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self.lock = threading.Lock()
        
    def acquire(self) -> float:
        """Acquire a token. Returns the time to wait if no tokens are available."""
        with self.lock:
            now = time.time()
            # Add new tokens based on time elapsed
            new_tokens = (now - self.last_update) * self.rate
            self.tokens = min(self.burst, self.tokens + new_tokens)
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return 0
            else:
                wait_time = (1 - self.tokens) / self.rate
                return wait_time

class PrizePicksScraper:
    """
    A scraper for the PrizePicks API to fetch sports, players, games, and projections data.
    """
    
    BASE_URL = "https://api.prizepicks.com"
    
    # Multiple user agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    ]
    
    # Multiple header configurations for rotation
    HEADER_TEMPLATES = [
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": "https://app.prizepicks.com/",
            "Origin": "https://app.prizepicks.com",
            "sec-ch-ua": '"Not/A)Brand";v="99", "Google Chrome";v="91"',
            "sec-ch-ua-mobile": "?0",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        },
        {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Referer": "https://prizepicks.com/",
            "Origin": "https://prizepicks.com",
            "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }
    ]
    
    # Cache settings
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
        
        # Initialize rate limiter (2 requests per second with burst of 5)
        self.rate_limiter = RateLimiter(rate=2.0, burst=5)
        
        # Setup retry strategy
        retry_strategy = Retry(
            total=5,  # total number of retries
            backoff_factor=1.5,  # exponential backoff
            status_forcelist=[429, 500, 502, 503, 504],  # status codes to retry on
            allowed_methods=["GET"],  # only retry on GET requests
            respect_retry_after_header=True  # respect Retry-After header
        )
        
        # Mount the retry adapter
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Initialize headers
        self._rotate_headers()
        
        # Request queue
        self.request_queue = deque()
        self.queue_lock = threading.Lock()
        
        logger.info("Initialized PrizePicksScraper with rate limiting and retry strategy")
    
    def _rotate_headers(self):
        """Rotate headers and user agent"""
        headers = random.choice(self.HEADER_TEMPLATES).copy()
        headers["User-Agent"] = random.choice(self.USER_AGENTS)
        headers["X-Device-ID"] = self._generate_device_id()
        
        # Add random viewport and screen resolution
        viewport_width = random.randint(1024, 1920)
        viewport_height = random.randint(768, 1080)
        headers["Viewport-Width"] = str(viewport_width)
        headers["Viewport-Height"] = str(viewport_height)
        
        self.session.headers.update(headers)
    
    def _handle_rate_limit(self, response: requests.Response) -> float:
        """Handle rate limit response and return wait time"""
        wait_time = 5  # default wait time
        
        # Check for Retry-After header
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                wait_time = float(retry_after)
            except (ValueError, TypeError):
                pass
        
        # Add jitter to avoid thundering herd
        wait_time += random.uniform(0.1, 1.0)
        
        logger.warning(f"Rate limited. Waiting {wait_time} seconds before retry")
        return wait_time
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a request to the PrizePicks API with rate limiting and retry handling.
        
        Args:
            endpoint: The API endpoint to request
            params: Optional query parameters
            
        Returns:
            The JSON response as a dictionary
        """
        url = f"{self.BASE_URL}/{endpoint}"
        
        # Wait for rate limiter
        wait_time = self.rate_limiter.acquire()
        if wait_time > 0:
            logger.info(f"Rate limit: waiting {wait_time:.2f} seconds")
            time.sleep(wait_time)
        
        # Add request to queue
        with self.queue_lock:
            self.request_queue.append((time.time(), url))
            
            # Remove old requests from queue (older than 1 minute)
            while self.request_queue and time.time() - self.request_queue[0][0] > 60:
                self.request_queue.popleft()
            
            # If queue is too long, wait
            if len(self.request_queue) > 10:
                wait_time = random.uniform(1.0, 3.0)
                logger.warning(f"Request queue full, waiting {wait_time:.2f} seconds")
                time.sleep(wait_time)
        
        try:
            # Rotate headers occasionally
            if random.random() < 0.2:  # 20% chance to rotate headers
                self._rotate_headers()
            
            logger.info(f"Making request to {url} with params {params}")
            response = self.session.get(url, params=params)
            
            # Log response details
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {response.headers}")
            
            if response.status_code == 429:
                wait_time = self._handle_rate_limit(response)
                time.sleep(wait_time)
                # Retry after waiting
                return self._make_request(endpoint, params)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RetryError as e:
            logger.error(f"Max retries exceeded: {e}")
            raise Exception(f"Failed to fetch data from PrizePicks API after multiple retries: {str(e)}")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise Exception(f"Failed to fetch data from PrizePicks API: {str(e)}")
    
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
            return self._projections_cache[cache_key]
        
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