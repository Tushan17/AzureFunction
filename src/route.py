import os
import requests

_AZURE_MAPS_URL = "https://atlas.microsoft.com/route/directions/json"


def optimize_route(
    start: dict,
    legs: list[dict],
    end: dict,
    subscription_key: str | None = None,
) -> dict:
    """
    Call the Azure Maps Route Directions API to find the optimal stop order.

    Parameters
    ----------
    start            : {"lat": float, "lon": float}
    legs             : [{"lat": float, "lon": float}, ...] intermediate stops
    end              : {"lat": float, "lon": float}
    subscription_key : Azure Maps key. Falls back to AZURE_MAPS_KEY env var.

    Returns
    -------
    {
        "optimizedLegs"          : legs reordered for the shortest trip,
                                   each entry keeps original fields and adds
                                   "originalIndex" (0-based position in input).
        "totalDistanceMeters"    : int,
        "totalTravelTimeSeconds" : int,
    }
    """
    key = subscription_key or os.environ.get("AZURE_MAPS_KEY")
    if not key:
        raise ValueError("Azure Maps subscription key not provided.")

    # Query format expected by Azure Maps: lat,lon:lat,lon:...
    all_points = [start] + legs + [end]
    query = ":".join(f"{p['lat']},{p['lon']}" for p in all_points)

    params = {
        "api-version": "1.0",
        "subscription-key": key,
        "query": query,
        "computeBestOrder": "true",
        "routeType": "fastest",
        "travelMode": "car",
    }

    response = requests.get(_AZURE_MAPS_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    route = data["routes"][0]
    summary = route["summary"]

    # optimizedWaypoints covers only the intermediate stops (legs), not start/end.
    # Each entry: {"providedIndex": <original 0-based>, "optimizedIndex": <new position>}
    optimized_waypoints = route.get("optimizedWaypoints", [])

    if optimized_waypoints:
        sorted_waypoints = sorted(optimized_waypoints, key=lambda w: w["optimizedIndex"])
        optimized_legs = [
            {**legs[w["providedIndex"]], "originalIndex": w["providedIndex"]}
            for w in sorted_waypoints
        ]
    else:
        # No reordering needed (single stop or already optimal)
        optimized_legs = [{**leg, "originalIndex": i} for i, leg in enumerate(legs)]

    return {
        "optimizedLegs": optimized_legs,
        "totalDistanceMeters": summary["lengthInMeters"],
        "totalTravelTimeSeconds": summary["travelTimeInSeconds"],
    }
