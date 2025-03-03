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

@app.get("/api/projections", response_model=List[Projection])
async def get_projections(
    sport_id: Optional[int] = None,
    player_name: Optional[str] = None,
    stat_type: Optional[str] = None,
    scraper: PrizePicksScraper = Depends(get_scraper)
):
    """
    Get all projections, with optional filters
    """
    try:
        return scraper.get_projections(sport_id, player_name, stat_type)
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

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 