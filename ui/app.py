from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.database.session import SessionLocal
from app.services.dashboard_service import DashboardService
from components.ai.ai_panel import render_ai_panel
from components.header import render_header
from components.kpi_section import render_kpis
from components.map.pydeck.map_legend import render_map_legend
from components.market_intelligence import render_market_intelligence
from components.sidebar import render_sidebar
from components.site_intelligence_panel import render_site_intelligence
from components.site_score_panel import render_site_score
from site_intelligence_view import site_section
from ui.navigation import dispatch_page


USE_PYDECK = True

if USE_PYDECK:
    from components.map.pydeck.map_section import render_map
else:
    from components.map.map_section import render_map


st.set_page_config(
    page_title="NRW Infrastructure & Facility Map",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="locked",
)


@st.cache_data(show_spinner=False, ttl=300)
def get_dashboard_data():
    session = SessionLocal()
    try:
        dashboard = DashboardService(session)
        return {
            "summary": dashboard.get_dashboard_summary(),
            "facilities": dashboard.get_facilities_for_map(),
            "energy_assets": dashboard.get_energy_assets_for_map(),
            "substations": dashboard.get_high_voltage_substations_for_map(),
            "high_voltage_lines": dashboard.get_high_voltage_lines_for_map(),
            "transformers": dashboard.get_transformers_for_map(),
            "latest_news": dashboard.get_latest_news(20),
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


def _selected_site_intelligence():
    facility_id = st.session_state.get("selected_facility_id")
    if not facility_id:
        return None

    start = time.perf_counter()
    intelligence = get_site_intelligence(facility_id)
    print(f"Site Intelligence: {time.perf_counter() - start:.3f}s")
    return intelligence


def _handle_map_selection(map_event):
    selection = getattr(map_event, "selection", None)
    objects = getattr(selection, "objects", None) or {}
    selected_facilities = objects.get("facilities", [])
    if not selected_facilities:
        return

    facility_id = selected_facilities[0].get("id")
    if facility_id and facility_id != st.session_state.get("selected_facility_id"):
        st.session_state.selected_facility_id = facility_id
        st.rerun()


def _render_map(
    *,
    facilities,
    energy_assets,
    substations,
    high_voltage_lines,
    transformers,
    show_facilities,
    show_substations,
    show_transformers,
    show_transmission,
    show_energy,
):
    with st.container(height=500):
        render_map_legend()
        return render_map(
            facilities=facilities,
            energy_assets=energy_assets,
            substations=substations,
            high_voltage_lines=high_voltage_lines,
            transformers=transformers,
            show_facilities=show_facilities,
            show_substations=show_substations,
            show_transformers=show_transformers,
            show_transmission=show_transmission,
            show_energy=show_energy,
        )


MAP_LAYER_SETTINGS = (
    ("setting_show_facilities", "Data centers", True),
    ("setting_show_substations", "HV substations", True),
    ("setting_show_transformers", "Transformers", True),
    ("setting_show_transmission", "Transmission lines", True),
    ("setting_show_energy", "Renewable energy", True),
)


def _layer_setting(key):
    return st.session_state[key]


def _initialize_map_layer_settings():
    for key, _, default in MAP_LAYER_SETTINGS:
        if key not in st.session_state:
            st.session_state[key] = default


def _store_map_layer_setting(key):
    st.session_state[key] = st.session_state[f"{key}_control"]


def _reset_map_layer_settings():
    for key, _, default in MAP_LAYER_SETTINGS:
        st.session_state[key] = default
        st.session_state[f"{key}_control"] = default


def _render_dashboard(data):
    render_header()
    render_kpis(data["summary"])

    map_col, ai_col = st.columns([7, 5], gap="medium")
    with map_col:
        map_event = _render_map(
            facilities=data["facilities"],
            energy_assets=data["energy_assets"],
            substations=data["substations"],
            high_voltage_lines=data["high_voltage_lines"],
            transformers=data["transformers"],
            show_facilities=_layer_setting("setting_show_facilities"),
            show_substations=_layer_setting("setting_show_substations"),
            show_transformers=_layer_setting("setting_show_transformers"),
            show_transmission=_layer_setting("setting_show_transmission"),
            show_energy=_layer_setting("setting_show_energy"),
        )
        _handle_map_selection(map_event)

    with ai_col:
        with st.container(height=500):
            render_ai_panel(compact=True)

    intelligence = _selected_site_intelligence()
    render_site_intelligence(intelligence)
    render_site_score(site_section(intelligence, "site_score"))
    render_market_intelligence(data["latest_news"][:5])


def _render_facilities(data):
    st.header("Facilities Intelligence")
    st.caption(
        "Explore mapped data centers and select a facility for live site analysis."
    )

    mapped = len(data["facilities"])
    total = data["summary"]["facilities"]
    metric_col, coverage_col = st.columns(2)
    metric_col.metric("Registered facilities", f"{total:,}")
    coverage = (mapped / total * 100) if total else 0
    coverage_col.metric("Mapped facilities", f"{mapped:,}", f"{coverage:.1f}% coverage")

    map_event = _render_map(
        facilities=data["facilities"],
        energy_assets=[],
        substations=[],
        high_voltage_lines=[],
        transformers=[],
        show_facilities=True,
        show_substations=False,
        show_transformers=False,
        show_transmission=False,
        show_energy=False,
    )
    _handle_map_selection(map_event)

    st.subheader("Facility Registry")
    st.dataframe(
        data["facilities"],
        column_order=("name", "company", "city", "country", "latitude", "longitude"),
        column_config={
            "name": "Facility",
            "company": "Operator",
            "city": "City",
            "country": "Country",
            "latitude": st.column_config.NumberColumn("Latitude", format="%.5f"),
            "longitude": st.column_config.NumberColumn("Longitude", format="%.5f"),
        },
        hide_index=True,
        width="stretch",
        height=320,
    )

    intelligence = _selected_site_intelligence()
    render_site_intelligence(intelligence)
    render_site_score(site_section(intelligence, "site_score"))


def _render_power_grid(data):
    st.header("Power Grid Intelligence")
    st.caption(
        "Inspect high-voltage substations, transmission corridors, transformers, and energy assets."
    )

    columns = st.columns(4)
    columns[0].metric("HV substations", f"{len(data['substations']):,}")
    columns[1].metric("Transmission lines", f"{len(data['high_voltage_lines']):,}")
    columns[2].metric("Transformers", f"{len(data['transformers']):,}")
    columns[3].metric("Energy assets", f"{len(data['energy_assets']):,}")

    _render_map(
        facilities=[],
        energy_assets=data["energy_assets"],
        substations=data["substations"],
        high_voltage_lines=data["high_voltage_lines"],
        transformers=data["transformers"],
        show_facilities=False,
        show_substations=True,
        show_transformers=True,
        show_transmission=True,
        show_energy=True,
    )


def _render_land_values(data):
    st.header("Land Value Intelligence")
    st.caption(
        "BORIS NRW land-value context for the facility currently selected on the map."
    )

    st.metric(
        "NRW average land value",
        f"€{data['summary']['average_land_value']:,.2f}/m²",
    )

    intelligence = _selected_site_intelligence()
    land = (intelligence or {}).get("land") or {}
    if not land:
        st.warning("Select a mapped facility to inspect its nearest land-value record.")
        return

    land_value = land.get("land_value_eur_m2")
    columns = st.columns(4)
    columns[0].metric(
        "Selected-site land value",
        f"€{land_value:,.2f}/m²" if land_value is not None else "Not available",
    )
    columns[1].metric("Municipality", land.get("municipality") or "Not available")
    columns[2].metric("District", land.get("district") or "Not available")
    columns[3].metric("Postal code", land.get("postal_code") or "Not available")

    render_site_score(site_section(intelligence, "site_score"))


def _render_news(data):
    st.header("News Intelligence")
    st.caption(
        "Recent company, facility, investment, and infrastructure signals from the loaded news corpus."
    )
    render_market_intelligence(data["latest_news"])


def _render_ai_assistant():
    st.header("AI Infrastructure Assistant")
    st.caption(
        "Ask grounded questions about facilities, grid access, land values, rankings, and recent news."
    )
    render_ai_panel(compact=False)


def _render_settings(data):
    st.header("Dashboard Settings")
    st.caption("Choose the default map layers and refresh cached dashboard data.")

    if st.session_state.pop("settings_data_refreshed", False):
        st.success("Dashboard data refreshed from the database.")

    st.subheader("Dashboard map layers")
    columns = st.columns(2)
    for index, (key, label, default) in enumerate(MAP_LAYER_SETTINGS):
        control_key = f"{key}_control"
        if control_key not in st.session_state:
            st.session_state[control_key] = st.session_state[key]
        with columns[index % 2]:
            st.toggle(
                label,
                key=control_key,
                on_change=_store_map_layer_setting,
                args=(key,),
            )

    action_col, reset_col = st.columns(2)
    with action_col:
        if st.button("Refresh dashboard data", type="primary", width="stretch"):
            get_dashboard_data.clear()
            get_site_intelligence.clear()
            st.session_state.settings_data_refreshed = True
            st.rerun()
    with reset_col:
        st.button(
            "Reset layer defaults",
            width="stretch",
            on_click=_reset_map_layer_settings,
        )

    st.subheader("Loaded data")
    status_columns = st.columns(3)
    status_columns[0].metric("Facilities", f"{data['summary']['facilities']:,}")
    status_columns[1].metric(
        "Power infrastructure",
        f"{data['summary']['power_infrastructure']:,}",
    )
    status_columns[2].metric("News signals", f"{data['summary']['news_signals']:,}")


css_file = Path(__file__).parent / "assets" / "styles.css"
if css_file.exists():
    st.markdown(f"<style>{css_file.read_text()}</style>", unsafe_allow_html=True)

data = get_dashboard_data()
facilities = data["facilities"]
_initialize_map_layer_settings()
if "selected_facility_id" not in st.session_state:
    st.session_state.selected_facility_id = facilities[0]["id"] if facilities else None

selected_page = render_sidebar()
dispatch_page(
    selected_page,
    {
        "Dashboard": lambda: _render_dashboard(data),
        "Facilities": lambda: _render_facilities(data),
        "Power Grid": lambda: _render_power_grid(data),
        "Land Values": lambda: _render_land_values(data),
        "News Intelligence": lambda: _render_news(data),
        "AI Assistant": _render_ai_assistant,
        "Settings": lambda: _render_settings(data),
    },
)
