from datetime import datetime
import time
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import uvicorn

from app.scraper import PrizePicksScraper
from app.models import Sport, Player, Game, Projection

app = FastAPI(
    title="PrizePicks Fantasy Webscraper API",
    description="A real-time API for PrizePicks fantasy sports data",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a dependency to get the scraper instance
def get_scraper():
    scraper = PrizePicksScraper()
    try:
        yield scraper
    finally:
        pass  # No cleanup needed for API-based scraper

@app.get("/")
async def root():
    return {"message": "Welcome to PrizePicks Fantasy Webscraper API"}

@app.head("/")
async def root_head():
    # HEAD requests should return the same headers as GET but no body
    # FastAPI will handle this automatically
    return {"message": "Welcome to PrizePicks Fantasy Webscraper API"}

@app.get("/api/sports", response_model=List[Sport])
async def get_sports(scraper: PrizePicksScraper = Depends(get_scraper)):
    """
    Get all available sports from PrizePicks
    """
    try:
        return scraper.get_sports()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sports: {str(e)}")

@app.get("/api/sports/{sport_id}", response_model=Dict[str, Any])
async def get_sport_data(
    sport_id: int,
    scraper: PrizePicksScraper = Depends(get_scraper)
):
    """
    Get data for a specific sport by ID
    """
    try:
        return scraper.get_sport_data(sport_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sport data: {str(e)}")

@app.get("/api/players", response_model=List[Player])
async def get_players(
    sport_id: Optional[int] = None,
    scraper: PrizePicksScraper = Depends(get_scraper)
):
    """
    Get all players with their projections, optionally filtered by sport
    """
    try:
        return scraper.get_players(sport_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch players: {str(e)}")

@app.get("/api/players/{player_name}", response_model=Player)
async def get_player_data(
    player_name: str,
    scraper: PrizePicksScraper = Depends(get_scraper)
):
    """
    Get data for a specific player by name
    """
    try:
        player = scraper.get_player_by_name(player_name)
        if not player:
            raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found")
        return player
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch player data: {str(e)}")

@app.get("/api/projections")
async def get_projections(
    sport_id: Optional[int] = None,
    player_name: Optional[str] = None,
    stat_type: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1, description="Page number, starting from 1"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Number of items per page"),
    scraper: PrizePicksScraper = Depends(get_scraper)
):
    """
    Get projections with optional pagination.
    
    If page and page_size are provided, returns paginated results with metadata.
    If pagination parameters are not provided, returns all results.
    """
    try:
        return scraper.get_projections(
            sport_id=sport_id, 
            player_name=player_name, 
            stat_type=stat_type,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch projections: {str(e)}")

@app.get("/api/games", response_model=List[Game])
async def get_games(
    sport_id: Optional[int] = None,
    scraper: PrizePicksScraper = Depends(get_scraper)
):
    """
    Get all games, optionally filtered by sport
    """
    try:
        return scraper.get_games(sport_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch games: {str(e)}")

@app.get("/api/games/{game_id}", response_model=Game)
async def get_game_data(
    game_id: str,
    scraper: PrizePicksScraper = Depends(get_scraper)
):
    """
    Get data for a specific game by ID
    """
    try:
        game = scraper.get_game_by_id(game_id)
        if not game:
            raise HTTPException(status_code=404, detail=f"Game with ID '{game_id}' not found")
        return game
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch game data: {str(e)}")
    
@app.get("/api/refresh/{sport_id}", response_model=Dict[str, Any])
async def refresh_sport_data(
    sport_id: int,
    scraper: PrizePicksScraper = Depends(get_scraper)
):
    """
    Refresh data for a specific sport by ID
    
    This endpoint triggers a refresh of all data (projections, players, games) for the specified sport.
    It may take some time to complete as it fetches fresh data from the PrizePicks API.
    """
    try:
        start_time = time.time()
        
        # Check if sport exists
        # sports = scraper.get_sports()
        # sport = next((s for s in sports if s.id == sport_id), None)
        
        # if not sport:
        #     raise HTTPException(status_code=404, detail=f"Sport with ID {sport_id} not found")
        
        # Get counts before refresh
        pre_projections = len(scraper.get_projections(sport_id=sport_id)['items'])
        pre_players = len(scraper.get_players(sport_id=sport_id))
        pre_games = len(scraper.get_games(sport_id=sport_id))
        
        # Call the existing refresh function
        scraper.refresh_all_data(sport_id=sport_id)
        
        # Get counts after refresh
        post_projections = len(scraper.get_projections(sport_id=sport_id)['items'])
        post_players = len(scraper.get_players(sport_id=sport_id))
        post_games = len(scraper.get_games(sport_id=sport_id))
        
        elapsed_time = time.time() - start_time
        
        return {
            "success": True,
            "sport": {
                "id": sport_id,
            },
            "refresh_time": datetime.now().isoformat(),
            "elapsed_time": elapsed_time,
            "projections": {
                "before": pre_projections,
                "after": post_projections,
                "difference": post_projections - pre_projections
            },
            "players": {
                "before": pre_players,
                "after": post_players,
                "difference": post_players - pre_players
            },
            "games": {
                "before": pre_games,
                "after": post_games,
                "difference": post_games - pre_games
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh sport data: {str(e)}")