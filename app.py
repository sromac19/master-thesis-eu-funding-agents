from __future__ import annotations

from datetime import UTC, date, datetime
from html import escape
from typing import Any

import httpx
import streamlit as st

from eu_funding_agents.reporting import build_client_pdf

RECOMMENDATION_API_URL = "http://127.0.0.1:8000/api/v1/recommendations/preview"
HISTORICAL_API_URL = "http://127.0.0.1:8000/api/v1/historical/similar"


def format_eur(value: float | None) -> str:
    if value is None:
        return "Not provided"
    if value >= 1_000_000:
        return f"€{value / 1_000_000:.1f}M"
    return f"€{value:,.0f}"


def format_percentage(value: float | None) -> str:
    return "Not provided" if value is None else f"{value:.0%}"


def format_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return parsed.strftime("%d %b %Y")


def status_label(value: str) -> str:
    return {"open": "Open", "forthcoming": "Opening soon"}.get(value, "Check official page")


def action_type_label(value: str | None) -> str:
    if not value or value.startswith("sedia_type:"):
        return "See the official call page for the activity type."
    return value


def user_friendly_reason(value: str) -> str:
    translations = {
        "Multilingual lexical and semantic match with the project description": (
            "The call covers topics that are similar to your project idea."
        ),
        "Lexical match": "The call uses terms that also appear in your project description.",
        "Call-specific formal criteria have not been human-verified": (
            "Confirm the applicant and partnership rules on the official call page."
        ),
        "Human verification": (
            "Confirm the applicant and partnership rules on the official call page."
        ),
    }
    return translations.get(value, value)


def detail_card(label: str, value: str) -> None:
    st.markdown(
        "<div class='detail-card'>"
        f"<div class='detail-label'>{escape(label)}</div>"
        f"<div class='detail-value'>{escape(value)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="EU Funding Agents", layout="wide")
st.markdown(
    """
    <style>
      .block-container {max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {
        background: rgba(76, 110, 245, 0.06);
        border: 1px solid rgba(76, 110, 245, 0.18);
        border-radius: 12px;
        padding: 0.8rem 1rem;
      }
      [data-testid="stMetricLabel"] p {
        font-size: 0.78rem;
        line-height: 1.15;
        white-space: normal;
      }
      [data-testid="stMetricValue"] {
        font-size: 1.35rem;
        overflow-wrap: anywhere;
      }
      [data-testid="stExpander"] {border-radius: 12px;}
      [data-testid="stExpander"] summary p {white-space: normal; line-height: 1.25;}
      .call-meta {color: #667085; font-size: 0.9rem; margin-bottom: 0.6rem;}
      .detail-card {
        min-height: 82px;
        background: rgba(76, 110, 245, 0.06);
        border: 1px solid rgba(76, 110, 245, 0.18);
        border-radius: 12px;
        padding: 0.75rem 0.9rem;
        margin-bottom: 0.75rem;
      }
      .detail-label {color: #667085; font-size: 0.78rem; line-height: 1.2;}
      .detail-value {font-size: 1.05rem; font-weight: 600; line-height: 1.3; margin-top: 0.3rem;}
      .app-footer {color: #667085; font-size: 0.82rem; margin-top: 2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Find EU funding for your project")
st.caption("Discover current EU calls and understand why they may fit your idea")
st.warning(
    "This tool helps you explore opportunities. Always confirm eligibility and deadlines "
    "on the official EU call page before applying."
)

with st.sidebar:
    st.header("About this prototype")
    st.success("Current EU call catalogue")
    st.markdown("Official call links are included with every result.")
    st.info("Eligibility is not automatic. The app highlights what you still need to check.")
    st.markdown("**How to use it**")
    st.markdown("1. Describe your project\n2. Review the best matches\n3. Open the official call")
    st.markdown("**Privacy**")
    st.caption(
        "In this local preview, your project profile is not saved and is not sent to an "
        "external AI model."
    )

with st.form("project-profile"):
    st.subheader("Tell us about your project")
    left, right = st.columns(2)
    with left:
        country = st.text_input(
            "Country (two-letter code)", value="HR", max_chars=2, help="For example: HR or DE"
        )
        organisation_type = st.selectbox(
            "Organisation type",
            (
                "Small or medium-sized company",
                "Startup",
                "Large company",
                "University",
                "Public body",
                "Non-profit organisation",
                "Other",
            ),
        )
    with right:
        sectors = st.multiselect(
            "Project area",
            ("Digital and industry", "Energy and environment", "Health", "Agriculture and food"),
        )
        budget = st.number_input(
            "Estimated project budget in EUR (optional)", min_value=0.0, value=None
        )
    with st.expander("Optional project details"):
        st.caption("Skip these fields if you are unsure.")
        trl = st.number_input(
            "Technology readiness level (TRL)",
            min_value=1,
            max_value=9,
            value=None,
            help=(
                "TRL is a 1–9 scale: 1 means early research and 9 means a solution already "
                "proven in real use."
            ),
        )
        has_consortium = st.selectbox(
            "Do you already have organisations you plan to apply with?",
            ("Not sure", "Yes", "No"),
            help="Some EU calls require several organisations from different countries.",
        )
    description = st.text_area(
        "Project description",
        height=180,
        placeholder=(
            "Describe the problem, your solution, who will use it and the impact you expect. "
            "You may write in Croatian or English."
        ),
    )
    submitted = st.form_submit_button(
        "Find matching calls", type="primary", use_container_width=True
    )

if submitted:
    profile = {
        "description": description,
        "country": country.upper(),
        "organisation_type": {
            "Small or medium-sized company": "SME",
            "Startup": "startup",
            "Large company": "large_company",
            "University": "university",
            "Public body": "public_body",
            "Non-profit organisation": "NGO",
            "Other": "other",
        }[organisation_type],
        "sectors": [
            {
                "Digital and industry": "digitalisation",
                "Energy and environment": "energy_environment",
                "Health": "health",
                "Agriculture and food": "agriculture_food",
            }[sector]
            for sector in sectors
        ],
        "trl": trl,
        "requested_budget_eur": budget,
        "has_consortium": {"Yes": True, "No": False}.get(has_consortium),
        "partner_countries": [],
    }
    try:
        response = httpx.post(
            RECOMMENDATION_API_URL,
            json={
                "profile": profile,
                "top_k": 10,
                "as_of": datetime.now(UTC).date().isoformat(),
            },
            timeout=90,
        )
        response.raise_for_status()
        report = response.json()
    except httpx.HTTPError as exc:
        st.error(f"The service is currently unavailable: {exc}")
    else:
        st.subheader("Best matching current calls")
        st.caption("🟢 Open now  ·  🟠 Opening soon")
        st.caption(f"Catalogue checked on {report['as_of']} · ranking method: {report['method']}")
        recommendations = report["recommendations"]
        official_link_count = sum(
            str(item["official_url"]).startswith("https://ec.europa.eu/")
            for item in recommendations
        )
        evidence_count = sum(bool(item["evidence"]) for item in recommendations)
        verification_count = sum(
            item["eligibility_status"] == "REQUIRES_VERIFICATION" for item in recommendations
        )
        first_metric, second_metric, third_metric, fourth_metric = st.columns(4)
        first_metric.metric("Matching calls", len(recommendations))
        second_metric.metric("Official links", official_link_count)
        third_metric.metric("Source excerpts", evidence_count)
        fourth_metric.metric("Need eligibility check", verification_count)
        for rank, item in enumerate(report["recommendations"], start=1):
            status_icon = "🟢" if item["call_status"] == "open" else "🟠"
            with st.expander(
                f"{status_icon} {rank}. {item['title']} · {item['days_remaining']} days left",
                expanded=rank == 1,
            ):
                st.markdown(
                    f"<div class='call-meta'>{item['programme']} · {item['call_id']}</div>",
                    unsafe_allow_html=True,
                )
                deadline_column, days_column, budget_column = st.columns(3)
                with deadline_column:
                    detail_card("Application deadline", format_date(item["deadline"]))
                with days_column:
                    detail_card("Time left", f"{item['days_remaining']} days")
                with budget_column:
                    detail_card("Total call budget", format_eur(item["budget_eur"]))
                rate_column, status_column = st.columns(2)
                with rate_column:
                    detail_card("Published funding rate", format_percentage(item["funding_rate"]))
                with status_column:
                    detail_card("Call status", status_label(item["call_status"]))
                st.caption(
                    "The total call budget may cover many projects and is not necessarily the "
                    "amount available to one applicant."
                )
                st.link_button("Open the official call", item["official_url"])

                match_tab, conditions_tab, evidence_tab = st.tabs(
                    ("Why this call", "Who can apply", "Official sources")
                )
                with match_tab:
                    reasons = [user_friendly_reason(value) for value in item["reasons_for"]]
                    st.success(
                        "Why it may fit: " + (" ".join(reasons) or "No clear match was found.")
                    )
                    if item["reasons_against"]:
                        st.warning(
                            "Possible concerns: "
                            + " ".join(user_friendly_reason(v) for v in item["reasons_against"])
                        )
                    checks = [user_friendly_reason(value) for value in item["missing_information"]]
                    check_text = " ".join(checks) or "Check the full rules on the official page."
                    st.warning(
                        "Eligibility not yet confirmed. This means the topic looks relevant, "
                        "but the app does not yet have enough verified rules to decide whether "
                        f"your organisation can apply. Next step: {check_text}"
                    )
                with conditions_tab:
                    st.write("**Funding activity**")
                    st.write(action_type_label(item["action_type"]))
                    st.write("**Applicant requirements**")
                    st.write(item["applicant_conditions"] or "Not available in the catalogue.")
                    st.write("**Partnership requirements**")
                    st.write(item["consortium_conditions"] or "Not available in the catalogue.")
                    st.caption(
                        "If information is missing here, it does not mean there are no rules. "
                        "Use the official call page for the final requirements."
                    )
                with evidence_tab:
                    if item["evidence"]:
                        for citation in item["evidence"]:
                            location = (
                                f"page {citation['page']}"
                                if citation["page"] is not None
                                else citation["section"] or "excerpt"
                            )
                            st.caption(f"{citation['document_name']} · {location}")
                            st.write(citation["excerpt"])
                            st.link_button("Open the official document", citation["source_url"])
                    else:
                        st.caption(
                            "No verified document excerpt is available in the local prototype. "
                            "Use the official call link above."
                        )
                st.caption(f"Catalogue data retrieved: {item['fetched_at']}")

        history_report: dict[str, Any] | None = None
        try:
            history_response = httpx.post(
                HISTORICAL_API_URL,
                json={"project_description": description, "top_k": 3},
                timeout=30,
            )
            history_response.raise_for_status()
            history_report = history_response.json()
        except httpx.HTTPError as exc:
            st.info(f"Similar funded projects are currently unavailable: {exc}")
        else:
            with st.expander("Explore similar funded projects (optional)"):
                st.caption(
                    "These are older EU-funded projects with similar themes. Use them for "
                    "inspiration only; they do not prove eligibility or define which partners "
                    "you need."
                )
                for project in history_report["similar_projects"]:
                    st.write(f"**{project['title']}** ({project['framework_programme']})")
                    st.link_button("View on CORDIS", project["official_url"])
        pdf_profile = {
            "description": description,
            "country": country.upper(),
            "organisation_type": organisation_type,
            "sectors": sectors,
            "requested_budget_eur": budget,
        }
        pdf_data = build_client_pdf(pdf_profile, report, max_calls=5)
        st.download_button(
            "Download client report (PDF)",
            data=pdf_data,
            file_name="eu-funding-opportunity-report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

st.markdown(
    '<div class="app-footer">EU Funding Agents · local research prototype · '
    "confirm all formal requirements on the official EU portal</div>",
    unsafe_allow_html=True,
)
