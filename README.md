# PrizePicks Fantasy Webscraper API

A real-time webscraper API for PrizePicks fantasy sports data. This API allows you to fetch player picks, odds, and other fantasy sports data from PrizePicks.

## Features

- Real-time data fetching from PrizePicks API
- Comprehensive endpoints for querying sports data
- Filter by sport, player, game, and more
- Compare odds and player statistics
- Caching system to reduce API calls and improve performance

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the API server:
   ```
   uvicorn app.main:app --reload
   ```
4. Access the API documentation at `http://localhost:8000/docs`

## API Endpoints

### Sports

- `GET /api/sports` - Get all available sports
- `GET /api/sports/{sport_id}` - Get detailed data for a specific sport

### Players

- `GET /api/players` - Get all players with their projections
  - Query parameters:
    - `sport_id` (optional): Filter by sport ID
- `GET /api/players/{player_name}` - Get data for a specific player by name

### Projections

- `GET /api/projections` - Get all projections/props
  - Query parameters:
    - `sport_id` (optional): Filter by sport ID
    - `player_name` (optional): Filter by player name
    - `stat_type` (optional): Filter by stat type (e.g., "Points", "Rebounds")

### Games

- `GET /api/games` - Get all games
  - Query parameters:
    - `sport_id` (optional): Filter by sport ID
- `GET /api/games/{game_id}` - Get data for a specific game by ID

## Usage Examples

### Get all NBA projections

```python
import requests

response = requests.get("http://localhost:8000/api/projections?sport_id=7")
nba_projections = response.json()
```

### Find projections for a specific player

```python
import requests

player_name = "LeBron James"
response = requests.get(f"http://localhost:8000/api/players/{player_name}")
player_data = response.json()
```

### Get all available sports

```python
import requests

response = requests.get("http://localhost:8000/api/sports")
sports = response.json()
```

## Sport IDs

Based on the PrizePicks API, here are some common sport IDs:

- NBA (Basketball): 7
- NFL (Football): 2
- MLB (Baseball): 3
- NHL (Hockey): 4
- PGA (Golf): 5
- Soccer: 9
- UFC/MMA: 10
- Tennis: 12
- WNBA: 19

Note that these IDs may change over time.

## Technical Details

This API uses direct calls to the PrizePicks API endpoints to fetch data. It implements a caching system to reduce the number of API calls and improve performance. The cache is refreshed every 15 minutes to ensure data is up-to-date.

## Technologies Used

- Python 3.8+
- FastAPI
- Requests
- Pydantic
- Uvicorn

## License

MIT