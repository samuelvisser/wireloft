from fastapi import APIRouter, HTTPException

from dailywire_api.records import DwMovieRecord

from .service import get_movie

router = APIRouter(prefix="/movies", tags=["DailyWire Movies"])


@router.get("/{movie_slug}", response_model=DwMovieRecord)
def movie_detail(movie_slug: str):
    try:
        return get_movie(movie_slug)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
