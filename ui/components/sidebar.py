import streamlit as st
from streamlit_option_menu import option_menu

from ui.navigation import PAGE_NAMES


def render_sidebar():
    with st.sidebar:
        # Professional UI Overrides: Aggressively targets Streamlit's inner block structure to strip top whitespace
        st.markdown("""
            <style>
                [data-testid="stSidebar"] {
                    min-width: 260px !important;
                    max-width: 260px !important;
                    background-color: #0B0F17 !important;
                    border-right: 1px solid rgba(255, 255, 255, 0.06);
                }
                
                /* Target Streamlit's inner sidebar container wrappers to completely remove top gap */
                [data-testid="stSidebarContent"] {
                    padding-top: 0rem !important;
                }
                [data-testid="stSidebarContent"] > div:first-child {
                    padding-top: 0rem !important;
                }
                [data-testid="stSidebarHeader"] {
                    display: none !important;
                }

                [data-testid="stSidebar"] .stSelectbox {
                    margin-bottom: -12px !important;
                }
                [data-testid="stSidebar"] .stSlider {
                    margin-bottom: -8px !important;
                }
                [data-testid="stSidebar"] label {
                    font-size: 11px !important;
                    font-weight: 500 !important;
                    color: #94A3B8 !important;
                    letter-spacing: 0.01em;
                }
                .stSelectbox div[data-baseweb="select"] > div {
                    background-color: #111827 !important;
                    border-color: rgba(255, 255, 255, 0.08) !important;
                    border-radius: 6px !important;
                    color: #F8FAFC !important;
                    min-height: 34px !important;
                }
            </style>
        """, unsafe_allow_html=True)

        # Enterprise Brand Header
        st.html("""
            <div style="padding: 12px 4px 16px 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); margin-bottom: 12px;">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div style="width: 32px; height: 32px; background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 14px; color: white; font-weight: 600; box-shadow: 0 2px 6px rgba(59, 130, 246, 0.2);">
                            ⚡
                        </div>
                        <div>
                            <div style="font-size: 13px; font-weight: 600; color: #F8FAFC; letter-spacing: -0.01em; line-height: 1.2;">NRW Intelligence</div>
                            <div style="font-size: 10px; font-weight: 400; color: #64748B; margin-top: 1px;">Infrastructure Grid</div>
                        </div>
                    </div>
                    <span style="font-size: 9px; font-weight: 600; background: rgba(16, 185, 129, 0.1); color: #34D399; padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(16, 185, 129, 0.2);">v2.4</span>
                </div>
            </div>
        """)

        selected = option_menu(
            menu_title=None,
            options=list(PAGE_NAMES),
            icons=[
                "house",
                "building",
                "lightning-charge",
                "geo-alt",
                "newspaper",
                "robot",
                "gear",
            ],
            default_index=0,
            key="primary_navigation",
            styles={
                "container": {
                    "padding": "0px",
                    "background-color": "transparent",
                },
                "icon": {
                    "color": "#64748B",
                    "font-size": "13px",
                },
                "nav-link": {
                    "font-size": "12px",
                    "font-weight": "400",
                    "text-align": "left",
                    "padding": "7px 10px",
                    "margin": "2px 0px",
                    "border-radius": "6px",
                    "color": "#94A3B8",
                    "transition": "all 0.15s ease",
                },
                "nav-link-selected": {
                    "background-color": "#1E293B",
                    "color": "#F8FAFC",
                    "font-weight": "500",
                    "border-left": "3px solid #3B82F6",
                    "border-radius": "0 6px 6px 0",
                    "box-shadow": "inset 1px 0 0 rgba(255, 255, 255, 0.05)",
                },
            },
        )

        st.html("""
            <div style="margin: 16px 0 8px 0; border-top: 1px solid rgba(255, 255, 255, 0.06); padding-top: 14px;">
                <div style="font-size: 10px; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: 0.08em; display: flex; align-items: center; gap: 6px;">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
                    Data Filters
                </div>
            </div>
        """)

        st.selectbox(
            "City Region",
            [
                "All Cities",
                "Cologne",
                "Düsseldorf",
                "Dortmund",
                "Essen",
                "Münster",
            ],
        )

        st.slider(
            "Capacity (MW)",
            0,
            100,
            (0, 100),
        )

        st.slider(
            "Substation Distance (km)",
            0,
            20,
            (0, 20),
        )

        st.slider(
            "Land Value (€/m²)",
            0,
            500,
            (0, 500),
        )

        st.slider(
            "Site Evaluation Score",
            0,
            100,
            (0, 100),
        )

        st.selectbox(
            "News Signals",
            [
                "All Signals",
                "Expansion",
                "Retrofit",
                "Construction",
                "Investment",
            ],
        )

        st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)

        st.button(
            "Apply Filters",
            width="stretch",
            type="primary",
        )

    return selected
