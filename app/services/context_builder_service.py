"""
Context Builder Service

Builds structured AI context from
Business Intelligence data.

This service does NOT call OpenAI.

Author:
NRW BI Platform
"""

from __future__ import annotations

from typing import Any


class ContextBuilderService:

    # =====================================================
    # Site Intelligence
    # =====================================================

    def build_site_context(
        self,
        site: dict,
        question: str,
    ) -> dict:

        facility = site["facility"]
        power = site["power"]
        land = site["land"]
        renewable = site["renewable_energy"]
        score = site["site_score"]

        return {
            "question": question,

            "facility": {
                "name": facility.name,
                "company": facility.company,
                "city": facility.city,
                "country": facility.country,
            },

            "site_score": {
                "overall_score": score["overall_score"],
                "rating": score["rating"],
                "grid_score": score["grid_score"],
                "transmission_score": score["transmission_score"],
                "transformer_score": score["transformer_score"],
                "renewable_score": score["renewable_score"],
                "land_score": score["land_score"],
                "expansion_score": score["expansion_score"],
            },

            "power": {
                "substation_distance": power["nearest_substation"]["distance_km"],
                "transmission_distance": power["nearest_high_voltage_line"]["distance_km"],
                "transmission_voltage": power["nearest_high_voltage_line"]["voltage"],
                "transformer_distance": power["nearest_transformer"]["distance_km"],
            },

            "land": {
                "municipality": land["municipality"],
                "land_value": land["land_value_eur_m2"],
            },

            "renewable": {
                "asset_count": renewable["asset_count"],
                "solar_kw": renewable["solar_kw"],
                "wind_kw": renewable["wind_kw"],
            },
        }

    # =====================================================
    # Comparison
    # =====================================================

    def build_comparison_context(
        self,
        left: dict,
        right: dict,
        question: str,
    ) -> dict:

        return {
            "question": question,
            "left": left,
            "right": right,
        }

    # =====================================================
    # Ranking
    # =====================================================

    def build_ranking_context(
        self,
        facilities: list[dict],
        ranking_type: str,
        question: str,
    ):

        return {

            "question": question,

            "ranking_type": ranking_type,

            "count": len(facilities),

            "facilities": facilities,
        }

    # =====================================================
    # Nearby Search
    # =====================================================

    def build_nearby_context(
        self,
        facilities: list[dict],
        latitude: float,
        longitude: float,
        radius_km: float,
        question: str,
    ) -> dict:

        return {
            "question": question,
            "origin": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "radius_km": radius_km,
            "facilities": facilities,
        }

    # =====================================================
    # Company Search
    # =====================================================

    def build_company_context(
        self,
        company: str,
        facilities: list[dict],
        question: str,
    ) -> dict:

        return {
            "question": question,
            "company": company,
            "facilities": facilities,
        }

    def _search_nearby(
        self,
        question: str,
    ) -> str:
        """
        Search nearby facilities around a city.
        """

        parsed = self.parser.parse(
            question,
        )

        city = parsed["city"]

        radius = (
            parsed["radius_km"]
            or 25
        )

        if city is None:

            return (
                "Please specify a city.\n\n"
                "Examples:\n"
                "• Find facilities within 20 km of Berlin\n"
                "• Show nearby data centers around Cologne\n"
                "• Find data centers near Düsseldorf"
            )

        city_facilities = (
            self.search.search_by_city(
                city,
            )
        )

        if not city_facilities:

            return (
                f"No facilities were found in '{city}'."
            )

        origin = city_facilities[0]

        facilities = (
            self.search.search_nearby(
                latitude=origin["latitude"],
                longitude=origin["longitude"],
                radius_km=radius,
            )
        )

        if not facilities:

            return (
                f"No facilities were found within "
                f"{radius} km of {city}."
            )

        context = (
            self.context_builder.build_nearby_context(
                facilities=facilities,
                latitude=origin["latitude"],
                longitude=origin["longitude"],
                radius_km=radius,
                question=question,
            )
        )

        prompt = NearbySearchPrompt.build(
            context,
        )

        return self.ai.generate(
            prompt,
        )
        
    # =====================================================
    # City Search
    # =====================================================

    def build_city_context(
        self,
        question: str,
        city: str,
        facilities: list,
    ) -> dict:

        return {
            "question": question,
            "city": city,
            "facilities": facilities,
        }

    # =====================================================
    # Generic
    # =====================================================

    def build(
        self,
        context_type: str,
        **kwargs: Any,
    ) -> dict:

        builders = {
            "site": self.build_site_context,
            "compare": self.build_comparison_context,
            "ranking": self.build_ranking_context,
            "nearby": self.build_nearby_context,
            "company": self.build_company_context,
            "city": self.build_city_context,
        }

        if context_type not in builders:
            raise ValueError(
                f"Unknown context type: {context_type}"
            )

        return builders[context_type](**kwargs)

     # =====================================================
    # News
    # =====================================================

    def build_news_context(
        self,
        news: list[dict],
        question: str,
    ) -> str:

        context = f"""
    User Question:
    {question}

    Latest News Intelligence

    """

        for item in news:

            context += f"""

    Title:
    {item['title']}

    Source:
    {item['source']}

    Published:
    {item['published']}

    Company:
    {item.get('company')}

    Facility:
    {item.get('facility_name')}

    City:
    {item.get('city')}

    Summary:
    {item['summary']}

    -----------------------------------
    """

        return context
