# Updated app.py
# Generated version based on your current architecture.

from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.database.session import SessionLocal
from app.services.dashboard_service import DashboardService

from components.sidebar import render_sidebar
from components.header import render_header
from components.kpi_section import render_kpis

# from components.ai_panel import render_ai_panel
from components.ai.ai_panel import render_ai_panel
from components.ranking_table import render_ranking_table
from components.analytics_panel import render_analytics_panel
from components.market_intelligence import render_market_intelligence
from components.city_charts import render_city_charts
from components.site_intelligence_panel import render_site_intelligence
# from components.map.legend import render_map_legend
from components.site_score_panel import render_site_score
from components.map.pydeck.map_legend import render_map_legend
from site_intelligence_view import site_section
import time

page_start = time.perf_counter()

USE_PYDECK = True

if USE_PYDECK:
    from components.map.pydeck.map_section import render_map
else:
    from components.map.map_section import render_map


st.set_page_config(
    page_title='NRW Infrastructure & Facility Map',
    page_icon='🗺️',
    layout='wide',
    initial_sidebar_state='locked',
)



@st.cache_data(show_spinner=False, ttl=300)
def get_dashboard_data():
    session = SessionLocal()
    try:
        dashboard = DashboardService(session)
        
        # ranking = dashboard.get_top_ranked_sites(5)

        
        return {
            'summary': dashboard.get_dashboard_summary(),
            'facilities': dashboard.get_facilities_for_map(),
            'energy_assets': dashboard.get_energy_assets_for_map(),
            'substations': dashboard.get_high_voltage_substations_for_map(),
            'high_voltage_lines': dashboard.get_high_voltage_lines_for_map(),
            'transformers': dashboard.get_transformers_for_map(),
            #  "top_ranked": ranking,
            "latest_news": dashboard.get_latest_news(5),
        }
    finally:
        session.close()

@st.cache_data(show_spinner=False, ttl=300)
def get_site_intelligence(facility_id):
    session = SessionLocal()
    try:
        return DashboardService(session).get_site_intelligence(facility_id)
    finally:
        session.close()

def get_clicked_facility(lat, lng):
    session = SessionLocal()
    try:
        return DashboardService(session).get_facility_from_click(lat, lng)
    finally:
        session.close()

css_file = Path(__file__).parent / 'assets' / 'styles.css'
if css_file.exists():
    st.markdown(f"<style>{css_file.read_text()}</style>", unsafe_allow_html=True)

data = get_dashboard_data()

summary = data['summary']
facilities = data['facilities']
energy_assets = data['energy_assets']
substations = data['substations']
high_voltage_lines = data['high_voltage_lines']
transformers = data['transformers']
# top_ranked = data["top_ranked"]
latest_news = data["latest_news"]

if 'selected_facility_id' not in st.session_state:
    st.session_state.selected_facility_id = facilities[0]['id'] if facilities else None

render_sidebar()
render_header()
render_kpis(summary)
# render_map_legend()
map_col, ai_col = st.columns([7,5], gap='medium')

with map_col:
    # st.write("Transformer count:", len(transformers))
    # st.write("Transformer sample:", transformers[:3])

    with st.container(height=500):
        render_map_legend()
        map_event = render_map(
            facilities=facilities,
            energy_assets=energy_assets,
            substations=substations,
            high_voltage_lines=high_voltage_lines,
            transformers=transformers,
            show_facilities=True,
            show_substations=True,
            show_transformers=True,
            show_transmission=True,
            show_energy=True,
        )

    
        
    if (
        map_event
        and map_event.selection
        and map_event.selection.objects
    ):
        selected = map_event.selection.objects.get("facilities", [])

        if selected:
            facility = selected[0]

            if (
                facility["id"]
                != st.session_state.selected_facility_id
            ):
                st.session_state.selected_facility_id = facility["id"]
                st.rerun()
        selected = map_event.selection.objects.get("facilities", [])

        if selected:
            facility = selected[0]

            if (
                facility["id"]
                != st.session_state.selected_facility_id
            ):
                st.session_state.selected_facility_id = facility["id"]
                st.rerun()

with ai_col:
    with st.container(height=500):
        render_ai_panel()

site_intelligence = None
if st.session_state.selected_facility_id:
    start = time.perf_counter()

    site_intelligence = get_site_intelligence(
        st.session_state.selected_facility_id
    )

    print(
        f"Site Intelligence: {time.perf_counter()-start:.3f}s"
    )

render_site_intelligence(site_intelligence)

render_site_score(
    site_section(site_intelligence, "site_score")
)

render_market_intelligence(latest_news)

# table_col, market_col = st.columns([1.5, 1], gap='medium')

# with table_col:
    # render_ranking_table(
    #     top_ranked,
    # )
    # st.write("ranking table")
# with analytics_col:
#     render_analytics_panel()
# with market_col:
    # render_market_intelligence(
    #     latest_news,
    # )
    # st.write("render markeet intelligence")   

# render_city_charts()