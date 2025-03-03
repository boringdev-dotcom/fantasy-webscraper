from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class Sport(BaseModel):
    """Model for a sport available on PrizePicks"""
    id: int
    name: str
    category: Optional[str] = None
    active: bool = True

class Player(BaseModel):
    """Model for a player on PrizePicks"""
    id: str
    name: str
    position: Optional[str] = None
    team: Optional[str] = None
    sport_id: int
    sport_name: str
    image_url: Optional[str] = None
    projections: Optional[List[Dict[str, Any]]] = None

class Projection(BaseModel):
    """Model for a player projection/prop on PrizePicks"""
    id: str
    player_id: str
    player_name: str
    sport_id: int
    sport_name: str
    game_id: Optional[str] = None
    stat_type: str
    line_score: float
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    is_active: bool = True
    opponent: Optional[str] = None
    
class Game(BaseModel):
    """Model for a game on PrizePicks"""
    id: str
    sport_id: int
    sport_name: str
    home_team: str
    away_team: str
    start_time: Optional[datetime] = None
    status: Optional[str] = None
    score: Optional[Dict[str, Any]] = None
    players: Optional[List[str]] = None

class APIResponse(BaseModel):
    """Generic API response model"""
    success: bool
    data: Any
    message: Optional[str] = None 