import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Configure logging
logger = logging.getLogger(__name__)

def generate_device_id() -> str:
    """
    Generate a random device ID for API requests.
    
    Returns:
        A UUID string to use as device ID
    """
    return str(uuid.uuid4())

def parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse a datetime string from the API.
    
    Args:
        date_str: ISO format datetime string
        
    Returns:
        Datetime object or None if parsing fails
    """
    if not date_str:
        return None
        
    try:
        # Handle ISO format with Z for UTC
        if date_str.endswith('Z'):
            date_str = date_str.replace('Z', '+00:00')
            
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse datetime: {date_str} - {e}")
        return None

def format_api_response(data: Any, success: bool = True, message: Optional[str] = None) -> Dict[str, Any]:
    """
    Format a consistent API response.
    
    Args:
        data: The data to return
        success: Whether the request was successful
        message: Optional message to include
        
    Returns:
        A formatted response dictionary
    """
    return {
        "success": success,
        "data": data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def get_sport_name_by_id(sport_id: int) -> str:
    """
    Get a sport name by its ID.
    
    Args:
        sport_id: The sport ID
        
    Returns:
        The sport name or "Unknown" if not found
    """
    sport_map = {
        2: "NFL",
        3: "MLB",
        4: "NHL",
        5: "PGA",
        7: "NBA",
        9: "Soccer",
        10: "UFC/MMA",
        12: "Tennis",
        19: "WNBA"
    }
    
    return sport_map.get(sport_id, "Unknown") 