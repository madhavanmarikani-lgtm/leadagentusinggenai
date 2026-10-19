"""SQLite Database Module for LeadGen AI with forward-compatible Apollo.io enrichment fields."""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")


def get_db_connection() -> sqlite3.Connection:
    """Creates a database connection with dict-like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Initializes SQLite schema for companies and people, including Apollo.io future fields."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Companies Table (enriched with company-level Apollo attributes)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                domain TEXT UNIQUE NOT NULL,
                website_url TEXT,
                country TEXT DEFAULT 'US',
                country_code TEXT DEFAULT 'US',
                industry TEXT DEFAULT 'SaaS',
                company_type TEXT DEFAULT 'Technology',
                key_need TEXT,
                summary TEXT,
                source_url TEXT,
                status TEXT DEFAULT 'New',

                -- Future Apollo.io Company Enrichment Fields
                apollo_org_id TEXT,
                employee_count TEXT,
                annual_revenue TEXT,
                technologies TEXT, -- JSON array of tech stack
                company_linkedin_url TEXT,
                primary_phone TEXT,
                city TEXT,
                state TEXT,
                apollo_enrichment_status TEXT DEFAULT 'pending', -- 'pending', 'enriched', 'failed'
                enriched_at TIMESTAMP,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 2. People Table (enriched with contact-level Apollo attributes)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                title TEXT,
                seniority TEXT DEFAULT 'C-Suite',
                email TEXT,
                email_status TEXT DEFAULT 'unverified', -- 'verified', 'guessed', 'unavailable'
                phone TEXT,
                linkedin_url TEXT,
                linkedin_search_url TEXT,

                -- Future Apollo.io Person Enrichment Fields
                apollo_person_id TEXT,
                apollo_headline TEXT,
                city TEXT,
                state TEXT,
                country TEXT,
                apollo_enrichment_status TEXT DEFAULT 'pending',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
            )
            """
        )

        # 3. Search History / Batches Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS search_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_prompt TEXT NOT NULL,
                target_geography TEXT,
                target_industry TEXT,
                leads_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.commit()
        print(f"[Database] SQLite schema verified and ready at: {DB_PATH}")


def save_company_and_people(lead_data: Dict[str, Any]) -> int:
    """
    Inserts or updates a discovered company and associates its decision makers.
    Uses clean domain as the primary unique key to avoid duplicate companies.
    """
    domain = lead_data.get("domain", "").lower().strip()
    if not domain:
        raise ValueError("Cannot save lead without a valid domain.")

    country = lead_data.get("country") or "Global / Unspecified"
    country_code = lead_data.get("country_code") or "GL"
    c_low = country.lower()
    if "sri lanka" in c_low or country_code == "LK":
        country = "Sri Lanka"
        country_code = "LK"
    elif "india" in c_low or country_code == "IN":
        country = "India"
        country_code = "IN"
    elif any(k in c_low for k in ["united kingdom", "uk", "london", "england", "scotland"]) or country_code == "GB":
        country = "United Kingdom"
        country_code = "GB"
    elif "germany" in c_low or country_code == "DE":
        country = "Germany"
        country_code = "DE"
    elif "canada" in c_low or country_code == "CA":
        country = "Canada"
        country_code = "CA"
    elif "australia" in c_low or country_code == "AU":
        country = "Australia"
        country_code = "AU"
    elif any(k in c_low for k in ["united states", "usa", "us"]) or country_code == "US":
        country = "United States"
        country_code = "US"
    elif country in ["Not specified", "unknown", "None"]:
        country = "Global / Unspecified"
        country_code = "GL"

    key_need = lead_data.get("key_need") or lead_data.get("summary", "")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert or ignore company
        cursor.execute(
            """
            INSERT INTO companies (
                company_name, domain, website_url, country, country_code,
                industry, company_type, key_need, summary, source_url,
                apollo_org_id, employee_count, annual_revenue, technologies,
                company_linkedin_url, primary_phone, city, state,
                apollo_enrichment_status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(domain) DO UPDATE SET
                company_name = excluded.company_name,
                website_url = excluded.website_url,
                country = excluded.country,
                country_code = excluded.country_code,
                industry = excluded.industry,
                key_need = excluded.key_need,
                summary = excluded.summary,
                apollo_org_id = COALESCE(excluded.apollo_org_id, companies.apollo_org_id),
                employee_count = COALESCE(excluded.employee_count, companies.employee_count),
                annual_revenue = COALESCE(excluded.annual_revenue, companies.annual_revenue),
                technologies = COALESCE(excluded.technologies, companies.technologies),
                company_linkedin_url = COALESCE(excluded.company_linkedin_url, companies.company_linkedin_url),
                primary_phone = COALESCE(excluded.primary_phone, companies.primary_phone),
                city = COALESCE(excluded.city, companies.city),
                state = COALESCE(excluded.state, companies.state),
                apollo_enrichment_status = COALESCE(excluded.apollo_enrichment_status, companies.apollo_enrichment_status),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                lead_data.get("company_name", domain),
                domain,
                lead_data.get("website_url", f"https://www.{domain}"),
                country,
                country_code,
                lead_data.get("industry", "Technology"),
                lead_data.get("company_type", "Digital Business"),
                key_need,
                lead_data.get("summary", ""),
                lead_data.get("source_url", ""),
                lead_data.get("apollo_org_id"),
                lead_data.get("employee_count"),
                lead_data.get("annual_revenue"),
                json.dumps(lead_data.get("technologies")) if lead_data.get("technologies") else None,
                lead_data.get("company_linkedin_url"),
                lead_data.get("primary_phone"),
                lead_data.get("city"),
                lead_data.get("state"),
                lead_data.get("apollo_enrichment_status", "pending"),
            ),
        )

        # Get company ID
        cursor.execute("SELECT id FROM companies WHERE domain = ?", (domain,))
        row = cursor.fetchone()
        company_id = row["id"]

        # Insert decision makers
        c_level_name = lead_data.get("c_level_name") or lead_data.get("decision_maker_name")
        c_level_title = lead_data.get("c_level_title") or lead_data.get("decision_maker_role") or "C-Level Executive"
        linkedin_search_url = lead_data.get("linkedin_search_url", "")
        direct_linkedin_url = lead_data.get("linkedin_url", "")
        email = lead_data.get("email") or lead_data.get("c_level_email", "")
        email_status = lead_data.get("email_status") or ("verified" if email else "unverified")
        phone = lead_data.get("phone") or lead_data.get("c_level_phone", "")
        apollo_person_id = lead_data.get("apollo_person_id")
        apollo_headline = lead_data.get("apollo_headline") or c_level_title
        person_status = "enriched" if email else lead_data.get("apollo_enrichment_status", "pending")

        if c_level_name and c_level_name.lower() not in ["not listed", "unknown", "executive team / not listed in snippet"]:
            # Check existing people for this company
            cursor.execute(
                "SELECT id, name, title, linkedin_url, email, phone FROM people WHERE company_id = ?",
                (company_id,),
            )
            existing_people = cursor.fetchall()

            # Check if this exact person name already exists
            matching_person = next((p for p in existing_people if p["name"].lower() == c_level_name.lower()), None)
            seniority = "C-Suite" if any(r in c_level_title.lower() for r in ["ceo", "cto", "coo", "founder", "managing director", "director", "owner", "president"]) else "Executive"

            if matching_person:
                # Update direct linkedin_url, email, phone if new info arrived
                cursor.execute(
                    """
                    UPDATE people SET
                        title = ?,
                        seniority = ?,
                        linkedin_url = COALESCE(?, linkedin_url),
                        email = COALESCE(?, email),
                        email_status = COALESCE(?, email_status),
                        phone = COALESCE(?, phone),
                        apollo_person_id = COALESCE(?, apollo_person_id),
                        apollo_headline = COALESCE(?, apollo_headline),
                        apollo_enrichment_status = COALESCE(?, apollo_enrichment_status)
                    WHERE id = ?
                    """,
                    (
                        c_level_title,
                        seniority,
                        direct_linkedin_url or None,
                        email or None,
                        email_status or None,
                        phone or None,
                        apollo_person_id,
                        apollo_headline,
                        person_status,
                        matching_person["id"],
                    ),
                )
            else:
                # Check if previous entry was just generic ("Executive Team", "Executive Leadership", "Team")
                generic_people = [p for p in existing_people if any(g in p["name"].lower() for g in ["executive team", "executive leadership", "team", "not listed"])]
                if generic_people:
                    # Update the generic record into the verified person!
                    cursor.execute(
                        """
                        UPDATE people SET
                            name = ?,
                            title = ?,
                            seniority = ?,
                            linkedin_url = ?,
                            linkedin_search_url = ?,
                            email = ?,
                            email_status = ?,
                            phone = ?,
                            apollo_person_id = ?,
                            apollo_headline = ?,
                            apollo_enrichment_status = ?
                        WHERE id = ?
                        """,
                        (
                            c_level_name,
                            c_level_title,
                            seniority,
                            direct_linkedin_url,
                            linkedin_search_url,
                            email,
                            email_status,
                            phone,
                            apollo_person_id,
                            apollo_headline,
                            person_status,
                            generic_people[0]["id"],
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO people (
                            company_id, name, title, seniority,
                            linkedin_url, linkedin_search_url,
                            email, email_status, phone,
                            apollo_person_id, apollo_headline, apollo_enrichment_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            company_id,
                            c_level_name,
                            c_level_title,
                            seniority,
                            direct_linkedin_url,
                            linkedin_search_url,
                            email,
                            email_status,
                            phone,
                            apollo_person_id,
                            apollo_headline,
                            person_status,
                        ),
                    )

        conn.commit()
        return company_id


def apply_apollo_enrichment_to_company(company_id: int, apollo_data: Dict[str, Any]) -> bool:
    """
    Updates a company and its people in SQLite with enriched Apollo organization and people data.
    """
    org = apollo_data.get("organization") or {}
    people = apollo_data.get("people") or []

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Update company attributes
        if org:
            techs = org.get("technologies") or []
            tech_json = json.dumps(techs) if isinstance(techs, list) else str(techs)
            cursor.execute(
                """
                UPDATE companies SET
                    apollo_org_id = COALESCE(?, apollo_org_id),
                    employee_count = COALESCE(?, employee_count),
                    annual_revenue = COALESCE(?, annual_revenue),
                    technologies = ?,
                    company_linkedin_url = COALESCE(?, company_linkedin_url),
                    primary_phone = COALESCE(?, primary_phone),
                    city = COALESCE(?, city),
                    state = COALESCE(?, state),
                    apollo_enrichment_status = 'enriched',
                    enriched_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    org.get("apollo_org_id") or None,
                    org.get("employee_count") or None,
                    org.get("annual_revenue") or None,
                    tech_json,
                    org.get("company_linkedin_url") or None,
                    org.get("primary_phone") or None,
                    org.get("city") or None,
                    org.get("state") or None,
                    company_id,
                ),
            )

        # 2. Update or insert people
        for p in people:
            p_name = p.get("name")
            if not p_name:
                continue

            cursor.execute("SELECT id, name FROM people WHERE company_id = ?", (company_id,))
            existing_people = cursor.fetchall()
            matching = next((ep for ep in existing_people if ep["name"].lower() == p_name.lower()), None)

            if matching:
                cursor.execute(
                    """
                    UPDATE people SET
                        title = COALESCE(?, title),
                        seniority = COALESCE(?, seniority),
                        email = COALESCE(?, email),
                        email_status = COALESCE(?, email_status),
                        phone = COALESCE(?, phone),
                        linkedin_url = COALESCE(?, linkedin_url),
                        city = COALESCE(?, city),
                        state = COALESCE(?, state),
                        country = COALESCE(?, country),
                        apollo_person_id = COALESCE(?, apollo_person_id),
                        apollo_headline = COALESCE(?, apollo_headline),
                        apollo_enrichment_status = 'enriched'
                    WHERE id = ?
                    """,
                    (
                        p.get("title") or None,
                        p.get("seniority") or None,
                        p.get("email") or None,
                        p.get("email_status") or None,
                        p.get("phone") or None,
                        p.get("linkedin_url") or None,
                        p.get("city") or None,
                        p.get("state") or None,
                        p.get("country") or None,
                        p.get("apollo_person_id") or None,
                        p.get("apollo_headline") or None,
                        matching["id"],
                    ),
                )
            else:
                generic = [ep for ep in existing_people if any(g in ep["name"].lower() for g in ["executive team", "executive leadership", "team", "not listed"])]
                if generic:
                    cursor.execute(
                        """
                        UPDATE people SET
                            name = ?,
                            title = ?,
                            seniority = ?,
                            email = ?,
                            email_status = ?,
                            phone = ?,
                            linkedin_url = ?,
                            city = ?,
                            state = ?,
                            country = ?,
                            apollo_person_id = ?,
                            apollo_headline = ?,
                            apollo_enrichment_status = 'enriched'
                        WHERE id = ?
                        """,
                        (
                            p_name,
                            p.get("title") or "Executive Leader",
                            p.get("seniority") or "C-Suite",
                            p.get("email") or "",
                            p.get("email_status") or "verified",
                            p.get("phone") or "",
                            p.get("linkedin_url") or "",
                            p.get("city") or "",
                            p.get("state") or "",
                            p.get("country") or "",
                            p.get("apollo_person_id") or "",
                            p.get("apollo_headline") or "",
                            generic[0]["id"],
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO people (
                            company_id, name, title, seniority,
                            email, email_status, phone, linkedin_url,
                            city, state, country,
                            apollo_person_id, apollo_headline, apollo_enrichment_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'enriched')
                        """,
                        (
                            company_id,
                            p_name,
                            p.get("title") or "Executive Leader",
                            p.get("seniority") or "C-Suite",
                            p.get("email") or "",
                            p.get("email_status") or "verified",
                            p.get("phone") or "",
                            p.get("linkedin_url") or "",
                            p.get("city") or "",
                            p.get("state") or "",
                            p.get("country") or "",
                            p.get("apollo_person_id") or "",
                            p.get("apollo_headline") or "",
                        ),
                    )

        conn.commit()
        return True


def get_all_companies(
    search: Optional[str] = None,
    industry: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieves companies with aggregated decision-makers and Apollo fields."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT
                c.*,
                (SELECT COUNT(*) FROM people WHERE company_id = c.id) as decision_makers_count
            FROM companies c
            WHERE 1=1
        """
        params: List[Any] = []

        if search:
            query += " AND (c.company_name LIKE ? OR c.domain LIKE ? OR c.summary LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term, term])

        if industry and industry.lower() != "all":
            query += " AND c.industry LIKE ?"
            params.append(f"%{industry.strip()}%")

        if status and status.lower() != "all":
            query += " AND c.status = ?"
            params.append(status.strip())

        query += " ORDER BY c.created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        companies = [dict(row) for row in cursor.fetchall()]

        # Attach decision makers to each company
        for comp in companies:
            cursor.execute(
                "SELECT * FROM people WHERE company_id = ? ORDER BY id ASC",
                (comp["id"],),
            )
            comp["people"] = [dict(p) for p in cursor.fetchall()]

        return companies


def get_company_by_id(company_id: int) -> Optional[Dict[str, Any]]:
    """Fetches full details of a specific company and its associated people."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        row = cursor.fetchone()
        if not row:
            return None

        company = dict(row)
        cursor.execute("SELECT * FROM people WHERE company_id = ?", (company_id,))
        company["people"] = [dict(p) for p in cursor.fetchall()]
        return company


def update_company_status(company_id: int, new_status: str) -> bool:
    """Updates the lead status (New, Contacted, Qualified, Archived)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE companies SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, company_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_company(company_id: int) -> bool:
    """Deletes a company and all associated people via CASCADE."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_stats() -> Dict[str, Any]:
    """Returns overview metrics for the dashboard."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM companies")
        total_companies = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM people")
        total_people = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT industry) FROM companies")
        total_industries = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM companies WHERE status = 'New'")
        new_leads = cursor.fetchone()[0]

        return {
            "total_companies": total_companies,
            "total_people": total_people,
            "total_industries": total_industries,
            "new_leads": new_leads,
        }


def export_leads_csv() -> str:
    """Exports all stored leads and decision-maker info into standard CSV format."""
    companies = get_all_companies(limit=1000)
    output = io.StringIO()
    writer = csv.writer(output)

    # Header with forward-compatible Apollo enrichment columns
    writer.writerow([
        "Company ID", "Company Name", "Domain", "Website URL", "Country",
        "Industry", "Key Need / Opportunity", "Summary", "Lead Status",
        "Decision Maker Name", "Decision Maker Title", "Seniority",
        "Work Email", "Phone", "LinkedIn Search URL", "LinkedIn Profile URL",
        "Apollo Org ID", "Employee Count", "Annual Revenue", "Technologies",
        "Enrichment Status", "Created At"
    ])

    for comp in companies:
        people = comp.get("people", [])
        if not people:
            writer.writerow([
                comp["id"], comp["company_name"], comp["domain"], comp["website_url"],
                comp["country"], comp["industry"], comp["key_need"], comp["summary"],
                comp["status"], "", "", "", "", "", "", "",
                comp.get("apollo_org_id", ""), comp.get("employee_count", ""),
                comp.get("annual_revenue", ""), comp.get("technologies", ""),
                comp.get("apollo_enrichment_status", "pending"), comp["created_at"]
            ])
        else:
            for p in people:
                writer.writerow([
                    comp["id"], comp["company_name"], comp["domain"], comp["website_url"],
                    comp["country"], comp["industry"], comp["key_need"], comp["summary"],
                    comp["status"], p.get("name", ""), p.get("title", ""), p.get("seniority", ""),
                    p.get("email", ""), p.get("phone", ""), p.get("linkedin_search_url", ""),
                    p.get("linkedin_url", ""), comp.get("apollo_org_id", ""),
                    comp.get("employee_count", ""), comp.get("annual_revenue", ""),
                    comp.get("technologies", ""), comp.get("apollo_enrichment_status", "pending"),
                    comp["created_at"]
                ])

    return output.getvalue()


# Initialize database automatically on import
init_db()
