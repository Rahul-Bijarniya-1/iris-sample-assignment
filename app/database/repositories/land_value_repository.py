from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.land_value import LandValue
from app.database.repositories.base_repository import BaseRepository
import math

class LandValueRepository(BaseRepository[LandValue]):
    """
    Repository for BORIS NRW land values.
    """

    def __init__(self, session: Session):
        super().__init__(session, LandValue)

    def find_by_id(
        self,
        land_value_id: int,
    ) -> LandValue | None:

        return self.session.get(
            LandValue,
            land_value_id,
        )

    def find_by_postal_code(
        self,
        postal_code: str,
    ) -> list[LandValue]:

        statement = (
            select(LandValue)
            .where(
                LandValue.postal_code == postal_code
            )
            .order_by(
                LandValue.municipality
            )
        )

        return list(
            self.session.scalars(statement)
        )

    def find_by_municipality(
        self,
        municipality: str,
    ) -> list[LandValue]:

        statement = (
            select(LandValue)
            .where(
                LandValue.municipality == municipality
            )
            .order_by(
                LandValue.postal_code
            )
        )

        return list(
            self.session.scalars(statement)
        )

    def find_municipality_location(
        self,
        municipality: str,
    ) -> dict | None:
        """
        Resolve a place name to a representative point (the centroid of
        its BORIS parcels, transformed to 4326) plus an average land
        value — lets the planner ask "near <place>" without a selected
        facility, which no other lookup in this codebase supports.
        """

        centroid = func.ST_Transform(
            func.ST_Centroid(
                func.ST_Collect(LandValue.geometry)
            ),
            4326,
        )

        statement = (
            select(
                func.ST_Y(centroid).label("latitude"),
                func.ST_X(centroid).label("longitude"),
                func.avg(
                    LandValue.land_value_eur_m2
                ).label("avg_land_value_eur_m2"),
                func.count().label("parcel_count"),
            )
            .where(
                func.lower(LandValue.municipality)
                == municipality.lower()
            )
        )

        result = self.session.execute(statement).first()

        if result is None or result.latitude is None:

            return None

        return {
            "municipality": municipality,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "avg_land_value_eur_m2": (
                round(result.avg_land_value_eur_m2, 2)
                if result.avg_land_value_eur_m2 is not None
                else None
            ),
            "parcel_count": result.parcel_count,
        }

    def count(self) -> int:

        statement = (
            select(func.count())
            .select_from(LandValue)
        )

        return self.session.scalar(statement)

    def delete_all(self) -> None:

        self.session.query(
            LandValue
        ).delete()

        self.session.commit()
    
    def find_nearest_land_value(
        self,
        latitude: float,
        longitude: float,
    ):
        """
        Returns the nearest valid BORIS land value.
        """

        point = func.ST_Transform(
            func.ST_SetSRID(
                func.ST_Point(
                    longitude,
                    latitude,
                ),
                4326,
            ),
            25832,
        )

        distance = (
            func.ST_Distance(
                LandValue.geometry,
                point,
            )
            / 1000
        ).label("distance_km")

        statement = (
            select(
                LandValue.id,
                LandValue.municipality,
                LandValue.district,
                LandValue.postal_code,
                LandValue.land_value_eur_m2,
                distance,
            )
            .where(
                LandValue.land_value_eur_m2.is_not(None),
            )
            .order_by(distance)
            .limit(1)
        )

        result = self.session.execute(statement).first()

        if result is None:
            return None

        value = result.land_value_eur_m2

        if value is None:
            return None

        if math.isnan(value):
            return None

        return {
            "id": result.id,
            "municipality": result.municipality,
            "district": result.district,
            "postal_code": result.postal_code,
            "land_value_eur_m2": (
                round(result.land_value_eur_m2, 2)
                if result.land_value_eur_m2 is not None
                else None
            ),
            "distance_km": (
                round(result.distance_km, 2)
                if result.distance_km is not None
                else None
            ),
        }