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
from pymongo import MongoClient
from pymongo.collection import Collection
from dotenv import load_dotenv
import os

load_dotenv()
import threading
from collections import deque
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
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
    With MongoDB integration for caching data.
    """
    
    BASE_URL = "https://api.prizepicks.com"
    
    # Multiple user agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
    ]
    
    # Single header template that matches PrizePicks web app exactly
    HEADER_TEMPLATES = [
        {
            "authority": "api.prizepicks.com",
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "dnt": "1",
            "origin": "https://app.prizepicks.com",
            "pragma": "no-cache",
            "referer": "https://app.prizepicks.com/",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
    
    def __init__(self, mongo_uri: str = os.getenv("MONGO_URI"), db_name: str = os.getenv("MONGO_DB")):
        """
        Initialize the scraper with MongoDB connection.
        
        Args:
            mongo_uri: MongoDB connection URI
            db_name: MongoDB database name
        """
        self.session = requests.Session()
        
        # Initialize MongoDB connection
        if not mongo_uri or not db_name:
            raise ValueError("MongoDB URI and database name must be provided in environment variables")
        
        try:
            # Initialize MongoDB connection with SSL certificate verification
            self.mongo_client = MongoClient(
                mongo_uri,
                tlsAllowInvalidCertificates=True,  # For development only
                tls=True  # Enable TLS
            )
            self.db = self.mongo_client[db_name]
            
            # Initialize collections
            self.projections_collection = self.db['projections']
            self.players_collection = self.db['players']
            self.games_collection = self.db['games']
            
            # Create indexes for better query performance
            self.projections_collection.create_index([("sport_id", 1)])
            self.projections_collection.create_index([("player_name", 1)])
            self.projections_collection.create_index([("last_updated", 1)])
            
            self.players_collection.create_index([("sport_id", 1)])
            self.players_collection.create_index([("name", 1)])
            
            self.games_collection.create_index([("sport_id", 1)])
            self.games_collection.create_index([("start_time", 1)])
            
            logger.info("Successfully connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise Exception(f"MongoDB connection failed: {str(e)}")
        
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
            # Generate session token
            session_token = str(uuid.uuid4())
            
            # Create base headers
            headers = self.HEADER_TEMPLATES[0].copy()
            headers["user-agent"] = random.choice(self.USER_AGENTS)
            headers["x-device-id"] = self._generate_device_id()
            headers["x-pp-session"] = session_token
            
            # Add cookies that match the web app
            cookies = {
                "_ga": f"GA1.1.{random.randint(1000000000, 9999999999)}.{int(time.time())}",
                "_ga_XXXXXXXXXX": f"GS1.1.{int(time.time())}.1.1.{int(time.time())}.0.0.0",
                "pp_session": session_token,
                "pp_device_id": headers["x-device-id"],
                "pp_guest": "true"
            }
            
            logger.info(f"Making request to {url} with params {params}")
            
            # Add small random delay
            time.sleep(random.uniform(0.5, 1.5))
            
            response = self.session.get(
                url, 
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=30
            )
            
            # Log response details
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {response.headers}")
            
            if response.status_code == 403:
                logger.warning("Received 403 error, retrying with new session...")
                time.sleep(random.uniform(1, 2))  # Add shorter delay on 403
                return self._make_request(endpoint, params)  # Retry with new session
            
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
        #Build
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
            "projections_count": len([projections['items']]),
            "games_count": len(games),
            "players_count": len(players),
            "projections": [p.dict() for p in projections['items'][:10]],  # Return only first 10 projections
            "games": [g.dict() for g in games[:10]],  # Return only first 10 games
            "players": [p.dict() for p in players[:10]]  # Return only first 10 players
        }
    
    def get_projections(
        self, 
        sport_id: Optional[int] = None, 
        player_name: Optional[str] = None,
        stat_type: Optional[str] = None,
        force_refresh: bool = False,
        page: Optional[int] = None,
        page_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get projections from MongoDB with optional pagination.
        
        Args:
            sport_id: Optional filter by sport ID
            player_name: Optional filter by player name
            stat_type: Optional filter by stat type
            force_refresh: Force refresh from API regardless of cache status
            page: Optional page number (starting from 1)
            page_size: Optional number of items per page
            
        Returns:
            If pagination is used: A dictionary with pagination info and projection objects
            If no pagination: A list of projection objects
        """
        # Build query for MongoDB
        query = {}
        if sport_id:
            query["sport_id"] = sport_id
        if player_name:
            query["player_name"] = {"$regex": player_name, "$options": "i"}
        if stat_type:
            query["stat_type"] = stat_type
        
        # Get total count
        total_count = self.projections_collection.count_documents(query)
        
        # Determine if pagination is being used
        use_pagination = page is not None and page_size is not None
        
        # Get data from MongoDB (with or without pagination)
        if use_pagination:
            # Calculate pagination parameters
            skip = (page - 1) * page_size
            projection_docs = list(self.projections_collection.find(query).skip(skip).limit(page_size))
        else:
            # Get all data
            projection_docs = list(self.projections_collection.find(query))
        
        # Convert to Projection objects
        projections = []
        for doc in projection_docs:
            # Remove MongoDB _id field
            doc_id = doc.pop("_id", None)
            # Convert last_updated to datetime if present
            doc.pop("last_updated", None)
            
            try:
                projection = Projection(**doc)
                projections.append(projection)
            except Exception as e:
                logger.warning(f"Failed to parse projection data from MongoDB: {e}")
        
        # Return appropriate response format based on whether pagination is used
        if use_pagination:
            # Calculate pagination metadata
            total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
            has_next = page < total_pages
            has_prev = page > 1
            
            # Return paginated response
            return {
                "items": projections,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev
                }
            }
        else:
            # For backward compatibility, return just the list if no pagination
            return {
                "items": projections,
                "total_count": total_count
            }
    
    def _refresh_projections_from_api(self, sport_id: int) -> None:
        """
        Refresh projections data for a specific sport from the PrizePicks API.
        
        Args:
            sport_id: The ID of the sport to refresh
        """
        # Prepare query parameters
        params = {
            "single_stat": True,
            "game_mode": "pickem",
            "league_id": sport_id
        }
        
        # For league_id 7 (which appears to be NFL), request more projections per page
        if sport_id == 7:
            params["per_page"] = 250
        else:
            params["per_page"] = 50  # Default for other leagues
        
        # Fetch projections data
        response = self._make_request("projections", params)
        
        if "data" not in response or "included" not in response:
            logger.error(f"Invalid API response for sport_id={sport_id}")
            return
        
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
        current_time = time.time()
        projection_docs = []
        player_docs = {}
        game_docs = {}
        
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
                
                # Extract stat type
                stat_type_value = proj_data["attributes"].get("stat_type", "Unknown")
                
                # Parse start time if available
                start_time = None
                if "start_time" in proj_data["attributes"] and proj_data["attributes"]["start_time"]:
                    try:
                        start_time = datetime.fromisoformat(proj_data["attributes"]["start_time"].replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass
                
                # Create projection document
                projection_doc = {
                    "id": proj_data["id"],
                    "player_id": player_id,
                    "player_name": player_name_value,
                    "sport_id": int(league_id),
                    "sport_name": league_data.get("attributes", {}).get("name", "Unknown"),
                    "game_id": game_id,
                    "stat_type": stat_type_value,
                    "line_score": float(proj_data["attributes"].get("line_score", 0)),
                    # description is currently used for team that player is playing against
                    "description": proj_data["attributes"].get("description"),
                    "start_time": start_time,
                    "is_active": proj_data["attributes"].get("is_active", True),
                    "opponent": game_data.get("attributes", {}).get("away_team"),
                    "last_updated": current_time
                }
                projection_docs.append(projection_doc)
                
                # Create player document
                if player_id not in player_docs:
                    player_docs[player_id] = {
                        "id": player_id,
                        "name": player_name_value,
                        "sport_id": int(league_id),
                        "sport_name": league_data.get("attributes", {}).get("name", "Unknown"),
                        "last_updated": current_time
                    }
                
                # Create game document
                if game_id and game_id not in game_docs:
                    game_docs[game_id] = {
                        "id": game_id,
                        "sport_id": int(league_id),
                        "sport_name": league_data.get("attributes", {}).get("name", "Unknown"),
                        "home_team": game_data.get("attributes", {}).get("home_team", "Unknown"),
                        "away_team": game_data.get("attributes", {}).get("away_team", "Unknown"),
                        "start_time": start_time,
                        "players": [player_id],
                        "last_updated": current_time
                    }
                elif game_id and player_id not in game_docs[game_id]["players"]:
                    game_docs[game_id]["players"].append(player_id)
                
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse projection data: {e}")
        
        # Update MongoDB collections
        if projection_docs:
            # Delete old projections for this sport
            self.projections_collection.delete_many({"sport_id": sport_id})
            # Insert new projections
            self.projections_collection.insert_many(projection_docs)
            logger.info(f"Updated {len(projection_docs)} projections for sport_id={sport_id}")
        
        # Update players collection
        if player_docs:
            for player_id, player_doc in player_docs.items():
                self.players_collection.update_one(
                    {"id": player_id},
                    {"$set": player_doc},
                    upsert=True
                )
            logger.info(f"Updated {len(player_docs)} players for sport_id={sport_id}")
        
        # Update games collection
        if game_docs:
            for game_id, game_doc in game_docs.items():
                self.games_collection.update_one(
                    {"id": game_id},
                    {"$set": game_doc},
                    upsert=True
                )
            logger.info(f"Updated {len(game_docs)} games for sport_id={sport_id}")
    
    def refresh_all_data(self, sport_id: Optional[int] = None) -> None:
        """
        Refresh all data from the PrizePicks API.
        
        Args:
            sport_id: Optional sport ID to refresh only that sport
        """
        if sport_id:
            logger.info(f"Refreshing all data for sport_id={sport_id}")
            self._refresh_projections_from_api(sport_id)
        else:
            # Get all sports and refresh each one
            sports = self.get_sports()
            for sport in sports:
                if sport.active:
                    logger.info(f"Refreshing data for sport: {sport.name} (ID: {sport.id})")
                    self._refresh_projections_from_api(sport.id)
                    # Add a small delay between requests
                    time.sleep(random.uniform(1.0, 2.0))
    
    def get_players(self, sport_id: Optional[int] = None) -> List[Player]:
        """
        Get players from MongoDB, optionally filtered by sport.
        
        Args:
            sport_id: Optional filter by sport ID
            
        Returns:
            A list of Player objects
        """
        # Build query for MongoDB
        query = {}
        if sport_id:
            query["sport_id"] = sport_id
        
        # Get data from MongoDB
        player_docs = list(self.players_collection.find(query))
        
        # Convert to Player objects
        players = []
        for doc in player_docs:
            # Remove MongoDB _id field
            doc_id = doc.pop("_id", None)
            doc.pop("last_updated", None)
            
            # Get projections for this player
            projections = self.get_projections(player_name=doc["name"])
            doc["projections"] = [p.dict() for p in projections['items']]
            
            try:
                player = Player(**doc)
                players.append(player)
            except Exception as e:
                logger.warning(f"Failed to parse player data from MongoDB: {e}")
        
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
        Get games from MongoDB, optionally filtered by sport.
        
        Args:
            sport_id: Optional filter by sport ID
            
        Returns:
            A list of Game objects
        """
        # Build query for MongoDB
        query = {}
        if sport_id:
            query["sport_id"] = sport_id
        
        # Get data from MongoDB
        game_docs = list(self.games_collection.find(query))
        
        # Convert to Game objects
        games = []
        for doc in game_docs:
            # Remove MongoDB _id field
            doc_id = doc.pop("_id", None)
            doc.pop("last_updated", None)
            
            try:
                game = Game(**doc)
                games.append(game)
            except Exception as e:
                logger.warning(f"Failed to parse game data from MongoDB: {e}")
        
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