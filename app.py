from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.security import OAuth2PasswordBearer
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from bson import ObjectId
import jwt
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI()

# MongoDB Configuration
MONGO_URI = os.getenv('MONGO_URI' )
DB_NAME = "OMG"

try:
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    client.admin.command('ping')
    logger.info("✅ MongoDB connection successful")
    db = client[DB_NAME]
    logger.info(f"✅ Using database: {DB_NAME}")
    logger.info(f"📂 Collections: {db.list_collection_names()}")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    raise

# JWT Configuration (keeping this in case you want some endpoints to remain private)
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key')
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 24 * 60

# OAuth2 Scheme (keeping this in case you want some endpoints to remain private)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(user_id: str):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

# Keeping the auth function but not using it for public endpoints
async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Public endpoints
@app.post("/api/generate_guest")
async def generate_guest():
    """Public endpoint to generate a guest user"""
    user_id = db.users.insert_one({
        "is_guest": True,
        "created_at": datetime.utcnow(),
        "balance": 0.0
    }).inserted_id
    
    token = create_access_token(str(user_id))
    return {
        "status": True,
        "token": token,
        "userId": str(user_id)
    }

@app.get("/api/user_details")
async def user_details(user_id: Optional[str] = None):
    """Public endpoint to get user details (now accepts user_id as query parameter)"""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id parameter is required")
    
    try:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "status": True,
            "userId": str(user["_id"]),
            "balance": user.get("balance", 0.0),
            "is_guest": user.get("is_guest", False)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user_id")

@app.get("/api/get_game_details")
async def get_game_details():
    """Public endpoint to get all game details"""
    try:
        categories = list(db.category.find({}, {"_id": 0}))
        bundles = list(db.bundles.find({}, {"_id": 0}))
        games = list(db.games.find({}, {"_id": 0}))
        
        return {
            "status": True,
            "categories": categories,
            "bundles": bundles,
            "games": games
        }
    except Exception as e:
        logger.error(f"Error fetching game data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch game data")

@app.get("/api/get_categories")
async def get_categories():
    """Public endpoint to get all categories"""
    try:
        categories = list(db.category.find({}))
        return {
            "status": True,
            "data": [
                {
                    "id": cat["id"],
                    "name": cat["name"],
                    "createdAt": cat.get("createdAt", "").isoformat()
                } for cat in categories
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch categories")

router = APIRouter(prefix="/api", tags=["Games"])

# Response model matching your game structure
class GameResponse(BaseModel):
    id: int
    name: str
    bundle_url: str
    category_names: List[str]
    image_url: str
    LastUpdate: Optional[str] = None

@router.get("/games", response_model=List[GameResponse])
async def get_all_games():
    """
    Public endpoint to fetch all games with their details:
    - id: Game ID
    - name: Game name
    - bundle_url: Download URL
    - category_names: List of categories
    - image_url: Game image URL
    """
    try:
        # Fetch all games from MongoDB
        games = list(db.games.find({}, {
            "_id": 0,       # Exclude MongoDB's _id
            "id": 1,        # Include game ID
            "name": 1,      # Include game name
            "bundle_url": 1,# Include bundle URL
            "category_names": 1,  # Include categories
            "image_url": 1,
            "LastUpdate": 1 
        }))
        
        return games
        
    except Exception as e:
        logging.error(f"Failed to fetch games: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve games. Please try again later."
        )


#test

# addinga new user
class CreateUserRequest(BaseModel):
    username: str

@app.post("/api/user/create")
def create_user(data: CreateUserRequest):
    if not data.username.strip():
        raise HTTPException(400, "Username required")

    user = {
        "username": data.username.strip(),
        "createdAt": datetime.utcnow(),
        "isGuest": True
    }

    result = db.users.insert_one(user)

    return {
        "status": True,
        "userId": str(result.inserted_id),
        "username": data.username
    }


@app.post("/api/world-record/submit")
def submit_world_record(payload: dict):
    """
    payload = {
        userId: str,
        gameId: str,
        score: int
    }
    """

    user_id = ObjectId(payload["userId"])
    game_id = ObjectId(payload["gameId"])
    score = int(payload["score"])

    record = db.world_records.find_one({"gameId": game_id})

    # No record yet OR new score beats world record
    if not record or score > record["score"]:
        db.world_records.update_one(
            {"gameId": game_id},
            {
                "$set": {
                    "userId": user_id,
                    "score": score,
                    "updatedAt": datetime.utcnow()
                }
            },
            upsert=True
        )

        return {
            "status": True,
            "newWorldRecord": True
        }

    return {
        "status": True,
        "newWorldRecord": False
    }

# tournament

@app.post("/api/tournament/submit")
def submit_tournament_score(payload: dict):
    """
    payload = {
        tournamentId: str,
        userId: str,
        username: str,
        score: int
    }
    """

    tournament_id = ObjectId(payload["tournamentId"])
    user_id = ObjectId(payload["userId"])
    username = payload["username"]
    score = int(payload["score"])

    # Get current top 50
    scores = list(
        db.tournament_scores
        .find({"tournamentId": tournament_id})
        .sort("score", -1)
    )

    # Check if user already exists
    existing = next((s for s in scores if s["userId"] == user_id), None)

    if existing:
        if score > existing["score"]:
            db.tournament_scores.update_one(
                {"_id": existing["_id"]},
                {"$set": {"score": score}}
            )
        return {"status": True}

    # If leaderboard not full OR score beats lowest in top 50
    if len(scores) < 50 or score > scores[-1]["score"]:
        db.tournament_scores.insert_one({
            "tournamentId": tournament_id,
            "userId": user_id,
            "username": username,
            "score": score
        })

        # Trim to top 50
        overflow = (
            db.tournament_scores
            .find({"tournamentId": tournament_id})
            .sort("score", -1)
            .skip(50)
        )

        ids_to_delete = [doc["_id"] for doc in overflow]
        if ids_to_delete:
            db.tournament_scores.delete_many({"_id": {"$in": ids_to_delete}})

        return {"status": True, "qualified": True}

    return {
        "status": True,
        "qualified": False,
        "approxRank": ">50"
    }
@app.get("/api/tournament/data")
def get_tournament_data():
    tournaments = list(db.tournaments.find())

    response = {
        "current": None,
        "last": None
    }

    for t in tournaments:
        leaderboard = list(
            db.tournament_scores
            .find({"tournamentId": t["_id"]})
            .sort("score", -1)
            .limit(50)
        )

        leaderboard_data = [
            {
                "rank": i + 1,
                "username": s["username"],
                "score": s["score"]
            }
            for i, s in enumerate(leaderboard)
        ]

        data = {
            "tournamentId": str(t["_id"]),
            "tournamentName": t["name"],
            "gameName": t["gameName"],
            "prizes": t["prizes"],
            "leaderboard": leaderboard_data
        }

        if t["weekType"] == "current":
            response["current"] = data
        elif t["weekType"] == "last":
            response["last"] = data

    return {
        "status": True,
        "data": response
    }

@app.get("/api/world-records")
def get_all_world_records():
    records = list(
        db.world_records.find({}, {
            "_id": 0,
            "gameId": 1,
            "score": 1
        })
    )

    return {
        "status": True,
        "data": records
    }

# Include the router
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

