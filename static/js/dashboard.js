/**
 * LeadGen AI — Dashboard Interactive JavaScript
 * Lead Generation Configuration locked strictly to ICP rules defined in config.py.
 * Handles live lead discovery, data table rendering, Apollo enrichment, and modals.
 */

document.addEventListener("DOMContentLoaded", () => {
    initActionButtonListeners();

    console.log(
        "%c[LeadGen AI]%c Dashboard Ready — Configuration strictly locked to defined ICP.",
        "color: #2563eb; font-weight: bold; font-size: 13px;",
        "color: #475569; font-size: 13px;"
    );
    console.log("[LeadGen AI] Target ICP: %cUS & UK | Mid-Market (50–200) | 5 Core Service Pillars", "color: #10b981; font-weight: bold;");
});

// Current session leads cache
let currentLeads = [];
let isDiscoveryRunning = false;

/**
 * Gathers locked ICP filter criteria from the configuration card.
 */
function collectFilterCriteria() {
    const getValues = (category) => {
        const chips = document.querySelectorAll(`.tag-chip[data-category="${category}"]`);
        return Array.from(chips).map(c => c.dataset.val || c.innerText.trim()).filter(Boolean);
    };

    return {
        mode: "manual",
        geographies: getValues("geographies"),
        industries: getValues("industries"),
        company_types: getValues("company_types"),
        services: getValues("services"),
        signals: getValues("signals"),
        titles: getValues("titles"),
        employees: document.getElementById("select-employees")?.value || "50-200",
        count: parseInt(document.getElementById("select-count")?.value || "10", 10),
    };
}

/**
 * Sets up action button listeners.
 */
function initActionButtonListeners() {
    const findBtn = document.getElementById("btn-find-leads");
    if (findBtn) {
        findBtn.addEventListener("click", executeLeadDiscovery);
    }
}

/**
 * Helper to resolve country label and clean badge pill styling (country name alone).
 */
function getCountryDisplay(country, countryCode) {
    const c = (country || "").toLowerCase();
    if (c.includes("india")) {
        return { pillClass: "country-in", label: "India" };
    } else if (c.includes("sri lanka")) {
        return { pillClass: "country-lk", label: "Sri Lanka" };
    } else if (c.includes("kingdom") || c === "uk") {
        return { pillClass: "country-gb", label: "United Kingdom" };
    } else if (c.includes("canada")) {
        return { pillClass: "country-ca", label: "Canada" };
    } else if (c.includes("germany")) {
        return { pillClass: "country-de", label: "Germany" };
    } else if (c.includes("australia")) {
        return { pillClass: "country-au", label: "Australia" };
    } else if (c.includes("united states") || c.includes("usa")) {
        return { pillClass: "country-us", label: "United States" };
    } else if (country && country !== "Not specified" && country !== "US" && country !== "unknown") {
        return { pillClass: "country-generic", label: country };
    }
    return { pillClass: "country-unknown", label: "Global / Unspecified" };
}

/**
 * Executes live lead discovery using the locked ICP criteria.
 */
async function executeLeadDiscovery() {
    if (isDiscoveryRunning) {
        console.warn("[Discovery] Search already running. Ignoring duplicate request.");
        return;
    }

    const criteria = collectFilterCriteria();
    const targetCount = criteria.count;

    isDiscoveryRunning = true;

    const findBtn = document.getElementById("btn-find-leads");
    const progressBanner = document.getElementById("search-progress-banner");
    const progressTitle = document.getElementById("progress-title");
    const progressSub = document.getElementById("progress-sub");

    console.group(
        "%c[Lead Discovery Execution]%c Launching discovery request for defined ICP...",
        "color: #2563eb; font-weight: bold; font-size: 13px;",
        "color: #64748b; font-size: 13px;"
    );
    console.log("Locked Criteria Payload:", criteria);
    console.groupEnd();

    // UI Button Loading State
    if (findBtn) {
        findBtn.disabled = true;
        findBtn.innerHTML = `<span class="progress-spinner" style="width: 14px; height: 14px; margin-right: 6px;"></span> Finding Leads...`;
    }
    if (progressBanner) {
        progressBanner.style.display = "flex";
        progressTitle.innerText = `AI Discovery Engine is searching ${targetCount} verified ICP companies...`;
        progressSub.innerText = `Targeting: ${criteria.geographies.join(", ")} | Mid-Market (50–200 employees) | ${criteria.services.slice(0, 3).join(", ")}...`;
    }

    const startTime = performance.now();

    try {
        const response = await fetch("/api/discover", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(criteria),
        });

        const data = await response.json();
        const durationSec = ((performance.now() - startTime) / 1000).toFixed(2);

        if (!data.success) {
            throw new Error(data.error || "Failed to discover leads.");
        }

        currentLeads = data.leads || [];

        console.group(
            `%c[Discovery Complete]%c Discovered & stored %c${currentLeads.length} qualified leads%c in ${durationSec}s!`,
            "color: #10b981; font-weight: bold; font-size: 13px;",
            "color: #334155; font-size: 13px;",
            "color: #10b981; font-weight: bold; font-size: 13px;",
            "color: #334155; font-size: 13px;"
        );
        console.log("Raw Leads Array:", currentLeads);
        if (currentLeads.length > 0) {
            console.table(currentLeads.map((l, i) => ({
                "#": i + 1,
                Company: l.company_name,
                Domain: l.domain,
                Country: l.country,
                Industry: l.industry,
                "Decision Maker": (l.people && l.people[0]) ? `${l.people[0].name} (${l.people[0].title || 'Executive'})` : "C-Level Leadership",
                "Key Need / Opportunity": l.key_need || l.summary
            })));
        }
        console.groupEnd();

        renderLeadsTable(currentLeads);

        // Update count badge in sidebar if present
        const navCount = document.getElementById("nav-leads-count");
        if (navCount && data.stats) {
            navCount.innerText = data.stats.total_companies;
        }

        showToast(`Successfully discovered and saved ${currentLeads.length} verified leads!`);

        // Scroll to results
        document.getElementById("results-section")?.scrollIntoView({ behavior: "smooth" });

    } catch (err) {
        console.error("%c[Discovery Error]:", "color: #ef4444; font-weight: bold;", err);
        showToast(`Discovery error: ${err.message}`, true);
    } finally {
        isDiscoveryRunning = false;

        if (findBtn) {
            findBtn.disabled = false;
            findBtn.innerHTML = `<span class="btn-icon">🔍</span> Find Leads`;
        }
        if (progressBanner) {
            progressBanner.style.display = "none";
        }
    }
}

/**
 * Renders the leads table from an array of company objects.
 */
function renderLeadsTable(leads) {
    const tableBody = document.getElementById("leads-table-body");
    const countTitle = document.getElementById("results-count-title");

    if (countTitle) {
        countTitle.innerText = `Extracted Leads (${leads.length} companies)`;
    }

    if (!tableBody) return;

    if (!leads || leads.length === 0) {
        tableBody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="7">
                    <div class="empty-state">
                        <span class="empty-icon">🎯</span>
                        <h3>No qualified leads found for this specific query</h3>
                        <p>Try broadening your criteria above (e.g. adding more industries or geographies) and search again.</p>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    let rowsHtml = "";
    leads.forEach((lead, index) => {
        const initial = (lead.company_name || "CO").substring(0, 2).toUpperCase();
        const countryInfo = getCountryDisplay(lead.country, lead.country_code);
        const people = lead.people || [];

        // Build Decision-Maker Designation display (Name FIRST, Designation SECOND)
        let dmHtml = "";
        if (people.length > 0) {
            dmHtml = '<div class="dm-designation-cell">';
            people.slice(0, 2).forEach(p => {
                const designation = p.title || "Founder & CEO";
                const directLink = p.linkedin_url ? `<a href="${escapeHtml(p.linkedin_url)}" target="_blank" title="Direct LinkedIn Profile" style="color: #0a66c2; text-decoration: none; margin-left: 4px; font-size: 0.82rem;">🔗</a>` : "";
                const pName = p.name ? `<span class="dm-name-label">${escapeHtml(p.name)}${directLink}</span>` : `<span class="dm-name-label">Executive</span>`;
                dmHtml += `
                    <div class="dm-entry">
                        ${pName}
                        <span class="dm-role-badge">${escapeHtml(designation)}</span>
                    </div>
                `;
            });
            if (people.length > 2) {
                dmHtml += `<span class="dm-more-count">+${people.length - 2} more</span>`;
            }
            dmHtml += '</div>';
        } else {
            dmHtml = `
                <div class="dm-entry">
                    <span class="dm-name-label">Executive Leadership</span>
                    <span class="dm-role-badge">C-Suite</span>
                </div>
            `;
        }

        // Full opportunity text (NO truncation)
        const opportunityText = lead.key_need || lead.summary || "B2B client matching ICP criteria";

        rowsHtml += `
            <tr class="lead-row" data-id="${lead.id || index}">
                <td>
                    <div class="company-cell">
                        <div class="company-logo">${initial}</div>
                        <div class="company-info">
                            <span class="company-name">${escapeHtml(lead.company_name)}</span>
                            <span class="company-status status-${(lead.status || 'new').toLowerCase()}">${lead.status || 'New'}</span>
                        </div>
                    </div>
                </td>
                <td>
                    <a href="${lead.website_url}" target="_blank" class="domain-pill">
                        ${escapeHtml(lead.domain)} <span class="external-icon">↗</span>
                    </a>
                </td>
                <td>
                    <div class="country-cell">
                        <span class="country-pill ${countryInfo.pillClass}">${escapeHtml(countryInfo.label)}</span>
                    </div>
                </td>


                <td>
                    <span class="industry-badge">${escapeHtml(lead.industry || 'Technology')}</span>
                </td>
                <td>
                    <p class="need-text">${escapeHtml(opportunityText)}</p>
                </td>
                <td>
                    ${dmHtml}
                </td>
                <td>
                    <div class="action-btn-group">
                        <button type="button" class="btn btn-sm btn-outline btn-view-details" onclick="openDetailsModalForLeadIndex(${index})">View Details</button>
                        <button type="button" class="btn btn-sm btn-dots-menu" title="More Options">⋮</button>
                    </div>
                </td>
            </tr>
        `;
    });

    tableBody.innerHTML = rowsHtml;
    console.log(`[Table Render] Rendered ${leads.length} rows in leads table.`);
}

/**
 * Opens details modal from the currently loaded memory cache.
 */
function openDetailsModalForLeadIndex(index) {
    const lead = currentLeads[index];
    if (!lead) return;
    console.log("[Modal] Viewing details for cached lead index", index, ":", lead.company_name);
    populateAndShowModal(lead);
}

/**
 * Opens details modal by fetching company details via API.
 */
async function openDetailsModalForId(companyId) {
    console.log(`[Modal] Fetching lead details for company ID: ${companyId}`);
    try {
        const res = await fetch(`/api/leads/${companyId}`);
        const data = await res.json();
        if (data.success && data.lead) {
            console.log(`[Modal] Received company details for: ${data.lead.company_name}`, data.lead);
            populateAndShowModal(data.lead);
        }
    } catch (e) {
        console.error("[Modal Error] Could not load lead details:", e);
        showToast("Could not load lead details.", true);
    }
}

/**
 * Fills modal content and shows the modal backdrop.
 */
let activeModalLeadId = null;

/**
 * Fills modal content and shows the modal backdrop.
 */
function populateAndShowModal(lead) {
    activeModalLeadId = lead.id;

    const nameEl = document.getElementById("modal-company-name");
    if (nameEl) nameEl.innerText = lead.company_name || "Company";

    const logoEl = document.getElementById("modal-company-logo");
    if (logoEl) logoEl.innerText = (lead.company_name || "CO").substring(0, 2).toUpperCase();
    
    const domainEl = document.getElementById("modal-company-domain");
    if (domainEl) {
        domainEl.innerText = `${lead.domain || 'website'} ↗`;
        domainEl.href = lead.website_url || (lead.domain ? `https://${lead.domain}` : '#');
    }

    const summaryEl = document.getElementById("modal-summary");
    if (summaryEl) summaryEl.innerText = lead.summary || "No overview provided.";

    const oppEl = document.getElementById("modal-opportunity");
    if (oppEl) oppEl.innerText = lead.key_need || "Identified as target B2B client matching ICP criteria.";

    // Meta Pills with Apollo Headcount & Revenue
    const metaContainer = document.getElementById("modal-meta-pills");
    if (metaContainer) {
        let pillsHtml = `
            <span class="industry-badge" style="margin-right: 0.5rem;">${escapeHtml(lead.industry || 'SaaS')}</span>
            <span class="industry-badge" style="margin-right: 0.5rem;">${escapeHtml(lead.company_type || 'Digital Agency')}</span>
            <span class="industry-badge" style="margin-right: 0.5rem;">${escapeHtml(lead.country || 'Global')}</span>
        `;
        if (lead.employee_count) {
            pillsHtml += `<span class="industry-badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); margin-right: 0.5rem;">👥 ${escapeHtml(lead.employee_count)} Employees</span>`;
        }
        if (lead.annual_revenue) {
            pillsHtml += `<span class="industry-badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); margin-right: 0.5rem;">💰 ${escapeHtml(lead.annual_revenue)}</span>`;
        }
        if (lead.city || lead.state) {
            const loc = [lead.city, lead.state].filter(Boolean).join(", ");
            pillsHtml += `<span class="industry-badge" style="margin-right: 0.5rem;">📍 ${escapeHtml(loc)}</span>`;
        }
        metaContainer.innerHTML = pillsHtml;
    }

    // Decision Makers List with direct verified email & phone
    const peopleList = document.getElementById("modal-people-list");
    const people = lead.people || [];

    if (people.length === 0) {
        peopleList.innerHTML = `<p style="color: #64748b; font-size: 0.85rem;">No individual decision-maker name parsed from snippet. Executive team identified.</p>`;
    } else {
        let pListHtml = "";
        people.forEach(p => {
            const directLinkedin = p.linkedin_url;
            const targetUrl = directLinkedin || p.linkedin_search_url;
            const btnLabel = directLinkedin ? "👔 View LinkedIn Profile" : "🔍 Find on LinkedIn";
            const linkedinBtn = targetUrl ? `
                <a href="${escapeHtml(targetUrl)}" target="_blank" class="btn btn-sm btn-primary">
                    ${btnLabel}
                </a>
            ` : "";

            let contactDetails = "";
            if (p.email) {
                contactDetails += `
                    <div style="margin-top: 6px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                        <a href="mailto:${escapeHtml(p.email)}" style="color: #3b82f6; font-size: 0.85rem; font-weight: 600; text-decoration: none;">
                            ✉️ ${escapeHtml(p.email)}
                        </a>
                        <span class="status-badge status-qualified" style="font-size: 0.65rem; padding: 2px 6px;">Verified Work Email</span>
                    </div>
                `;
            }
            if (p.phone) {
                contactDetails += `
                    <div style="margin-top: 4px;">
                        <a href="tel:${escapeHtml(p.phone)}" style="color: #10b981; font-size: 0.85rem; text-decoration: none; font-weight: 500;">
                            📞 Direct Dial: ${escapeHtml(p.phone)}
                        </a>
                    </div>
                `;
            }

            pListHtml += `
                <div class="person-card">
                    <div>
                        <div class="person-name">${escapeHtml(p.name)}</div>
                        <div class="person-title">${escapeHtml(p.title || 'Executive Leadership')}</div>
                        ${contactDetails}
                    </div>
                    ${linkedinBtn}
                </div>
            `;
        });
        peopleList.innerHTML = pListHtml;
    }

    // Technologies & Tech stack rendering
    const techContainer = document.getElementById("modal-apollo-techs");
    if (techContainer) {
        let techs = lead.technologies;
        if (typeof techs === "string") {
            try { techs = JSON.parse(techs); } catch (e) { techs = []; }
        }
        if (Array.isArray(techs) && techs.length > 0) {
            techContainer.innerHTML = `
                <div style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 4px; font-weight: 600;">Technologies Detected:</div>
                <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                    ${techs.map(t => `<span class="industry-badge" style="font-size: 0.72rem; padding: 2px 6px;">⚡ ${escapeHtml(t)}</span>`).join("")}
                </div>
            `;
        } else {
            techContainer.innerHTML = "";
        }
    }

    // Apollo Enrichment Button & Status Badge
    const statusBadge = document.getElementById("modal-apollo-status-badge");
    const apolloBtn = document.getElementById("btn-modal-apollo");
    if (statusBadge) {
        if (lead.apollo_enrichment_status === "enriched") {
            statusBadge.innerHTML = `<span style="color: #10b981; font-weight: 600;">✅ Enriched via Apollo B2B Sync</span>`;
            if (apolloBtn) apolloBtn.innerText = "🔄 Re-enrich with Apollo";
        } else {
            statusBadge.innerHTML = `<span style="color: #64748b;">Not yet enriched with Apollo</span>`;
            if (apolloBtn) apolloBtn.innerText = "⚡ Enrich with Apollo";
        }
    }

    const visitBtn = document.getElementById("modal-visit-site");
    if (visitBtn) {
        visitBtn.href = lead.website_url || `https://${lead.domain}`;
    }

    const modal = document.getElementById("details-modal");
    if (modal) modal.style.display = "flex";
}

function closeDetailsModal() {
    const modal = document.getElementById("details-modal");
    if (modal) modal.style.display = "none";
    activeModalLeadId = null;
    console.log("[Modal] Closed details modal.");
}

/**
 * Triggers live Apollo.io enrichment for the currently opened modal lead.
 */
async function enrichCurrentLeadWithApollo() {
    if (!activeModalLeadId) return;

    const btn = document.getElementById("btn-modal-apollo");
    const statusBadge = document.getElementById("modal-apollo-status-badge");

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="progress-spinner" style="width: 12px; height: 12px; margin-right: 4px;"></span> Enriching...`;
    }
    if (statusBadge) statusBadge.innerText = "Connecting to Apollo.io...";

    try {
        let res = await fetch(`/api/leads/${activeModalLeadId}/enrich-apollo`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        let data = await res.json();

        if (data.requires_key) {
            const userKey = prompt("Apollo API Key required.\nPlease paste your Apollo API Key (from apollo.io -> Settings -> API Keys):");
            if (!userKey || !userKey.trim()) {
                showToast("Apollo API key is required to enrich.", true);
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `⚡ Enrich with Apollo`;
                }
                if (statusBadge) statusBadge.innerText = "Key required";
                return;
            }
            // Retry with user-provided key
            res = await fetch(`/api/leads/${activeModalLeadId}/enrich-apollo`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ apollo_api_key: userKey.trim() })
            });
            data = await res.json();
        }

        if (data.success && data.lead) {
            showToast("⚡ Successfully enriched with Apollo! Verified email, phone, and revenue added.");
            populateAndShowModal(data.lead);

            // Update leads cache if in view
            const idx = currentLeads.findIndex(l => l.id === activeModalLeadId);
            if (idx !== -1) {
                currentLeads[idx] = data.lead;
                renderLeadsTable(currentLeads);
            }
        } else {
            showToast(data.message || data.error || "Apollo could not find profile.", true);
            if (statusBadge) statusBadge.innerText = "Profile not indexed";
        }
    } catch (err) {
        console.error("[Apollo UI Error]:", err);
        showToast(`Apollo enrichment failed: ${err.message}`, true);
        if (statusBadge) statusBadge.innerText = "Enrichment error";
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `⚡ Enrich with Apollo`;
        }
    }
}

/**
 * Helper to show toast alerts.
 */
function showToast(message, isError = false) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = "toast";
    if (isError) {
        toast.style.borderColor = "#ef4444";
        toast.style.background = "#450a0a";
    }
    toast.innerText = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 200);
    }, 4000);
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/**
 * Toggles responsive sidebar collapse / expansion
 */
function toggleSidebar() {
    const sidebar = document.querySelector(".sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (!sidebar) return;
    if (window.innerWidth <= 900) {
        const isOpen = sidebar.classList.toggle("open");
        if (backdrop) backdrop.classList.toggle("active", isOpen);
    } else {
        sidebar.classList.toggle("collapsed");
    }
}

// Auto-close mobile drawer when navigation links are clicked
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".sidebar-nav .nav-item").forEach(item => {
        item.addEventListener("click", () => {
            if (window.innerWidth <= 900) {
                const sidebar = document.querySelector(".sidebar");
                const backdrop = document.getElementById("sidebar-backdrop");
                if (sidebar) sidebar.classList.remove("open");
                if (backdrop) backdrop.classList.remove("active");
            }
        });
    });
});

/**
 * Filter repository leads table on consolidated dashboard / leads section.
 */
function filterRepositoryTable() {
    const query = document.getElementById("repo-search")?.value.toLowerCase().trim() || "";

    let visibleCount = 0;
    document.querySelectorAll("#repo-table-body .lead-row").forEach(row => {
        const text = row.innerText.toLowerCase();
        const isVisible = !query || text.includes(query);
        row.style.display = isVisible ? "" : "none";
        if (isVisible) visibleCount++;
    });

    console.log(`[Repository Filter] Query: "${query}" -> Showing ${visibleCount} rows`);
}

/**
 * Deletes lead row from SQLite database.
 */
async function deleteLeadRow(companyId) {
    if (!confirm("Are you sure you want to delete this lead?")) return;

    console.log(`[Lead Action] Deleting lead ID ${companyId}...`);
    try {
        const res = await fetch(`/api/leads/${companyId}`, { method: "DELETE" });
        const data = await res.json();
        if (data.success) {
            document.querySelectorAll(`.lead-row[data-id="${companyId}"]`).forEach(el => el.remove());
            currentLeads = currentLeads.filter(l => l.id !== companyId);
            console.log(`[Lead Action] Lead ID ${companyId} deleted successfully.`);
            showToast("Lead removed from database.");
            // Update counts if present
            const countEl = document.getElementById("stat-companies");
            if (countEl) {
                const cur = parseInt(countEl.innerText) || 0;
                if (cur > 0) countEl.innerText = cur - 1;
            }
        } else {
            showToast("Failed to delete lead from database.", true);
        }
    } catch (e) {
        console.error("[Lead Action Error] Error deleting lead:", e);
        showToast("Error deleting lead.", true);
    }
}
