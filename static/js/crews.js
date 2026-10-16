// The crew sizes and durations below are illustrative planning assumptions, not
// quotes from real contractors. Edit the PROJECTS list to change what the page recommends.

// Data from the server (see the crew-data script in crews.html):
// the hourly rate for each specialty comes from CREW_RATES in services/crews.py, so
// this page and the estimates saved with projects always use the same rates.
const PAGE_DATA = JSON.parse(document.getElementById("crew-data").textContent);
const RATES = PAGE_DATA.rates;

// Each size lists its crew. "days" is [shortest, longest] for that specialty, so
// a trade that only works part of the job is only counted for those days.
// "days" on the size itself is the completion range for the whole project.
const PROJECTS = [
    {
        id: "fence", scale: "small", category: "Outdoor construction", name: "Wooden fence",
        description: "Post-and-board privacy fence with posts set in concrete and one gate.",
        icon: "M6 40h36M10 40V14l3-4 3 4v26M22 40V14l3-4 3 4v26M34 40V14l3-4 3 4v26M6 20h36M6 32h36",
        sizes: [
            { id: "75ft", label: "75 ft", note: "Side yard", days: [2, 3], crew: [
                { role: "carpenter", workers: 2, days: [2, 3] }, { role: "general", workers: 1, days: [1, 2] }] },
            { id: "150ft", label: "150 ft", note: "Backyard", typical: true, days: [3, 5], crew: [
                { role: "carpenter", workers: 2, days: [3, 5] }, { role: "general", workers: 2, days: [2, 3] }] },
            { id: "300ft", label: "300 ft", note: "Full perimeter", days: [6, 8], crew: [
                { role: "carpenter", workers: 3, days: [6, 8] }, { role: "general", workers: 2, days: [4, 6] }] },
        ],
    },
    {
        id: "deck", scale: "small", category: "Outdoor construction", name: "Wooden deck",
        description: "Raised pressure-treated deck with railing and a set of steps.",
        icon: "M4 24h40v4H4zM8 28v14M24 28v14M40 28v14M6 24V12h36v12M14 12v12M22 12v12M30 12v12",
        sizes: [
            { id: "12x12", label: "12 × 12 ft", note: "Small landing", days: [4, 6], crew: [
                { role: "carpenter", workers: 2, days: [4, 6] }, { role: "general", workers: 1, days: [2, 3] }] },
            { id: "16x20", label: "16 × 20 ft", note: "Family deck", typical: true, days: [7, 10], crew: [
                { role: "carpenter", workers: 3, days: [7, 10] }, { role: "general", workers: 1, days: [3, 5] }] },
            { id: "multi", label: "Multi-level", note: "With lighting", days: [12, 16], crew: [
                { role: "carpenter", workers: 4, days: [12, 16] }, { role: "general", workers: 2, days: [5, 8] },
                { role: "electrician", workers: 1, days: [1, 2] }] },
        ],
    },
    {
        id: "patio", scale: "small", category: "Outdoor construction", name: "Concrete patio",
        description: "Formed and poured concrete patio on a compacted gravel base.",
        icon: "M4 34l10-14h30l-10 14zM14 20v4M44 20v4M34 34v4M4 34v4h30M44 24L34 38",
        sizes: [
            { id: "150sqft", label: "150 sq ft", note: "Small seating area", typical: true, days: [2, 3], crew: [
                { role: "mason", workers: 2, days: [2, 3] }, { role: "general", workers: 2, days: [1, 2] }] },
            { id: "400sqft", label: "400 sq ft", note: "Large patio", days: [3, 5], crew: [
                { role: "mason", workers: 3, days: [3, 5] }, { role: "general", workers: 2, days: [2, 3] }] },
        ],
    },
    {
        id: "shed", scale: "small", category: "Outdoor construction", name: "Storage shed",
        description: "Framed wood shed on a gravel or block base with a shingle roof.",
        icon: "M8 40V20L24 8l16 12v20zM18 40V28h12v12M24 28v12",
        sizes: [
            { id: "8x10", label: "8 × 10 ft", note: "Garden tools", days: [2, 4], crew: [
                { role: "carpenter", workers: 2, days: [2, 4] }, { role: "general", workers: 1, days: [1, 2] }] },
            { id: "12x16", label: "12 × 16 ft", note: "Workshop size", typical: true, days: [4, 6], crew: [
                { role: "carpenter", workers: 2, days: [4, 6] }, { role: "roofer", workers: 1, days: [1, 2] },
                { role: "general", workers: 1, days: [2, 3] }] },
        ],
    },
    {
        id: "painting", scale: "small", category: "Repairs & renovation", name: "Interior painting",
        description: "Patch, prime and paint walls and ceilings with two coats.",
        icon: "M8 8h26v10H8zM34 13h6v12H22v6M20 31h4v13h-4z",
        sizes: [
            { id: "room", label: "One room", note: "Up to 14 × 14 ft", days: [1, 2], crew: [
                { role: "painter", workers: 1, days: [1, 2] }] },
            { id: "floor", label: "One floor", note: "4–5 rooms", typical: true, days: [3, 4], crew: [
                { role: "painter", workers: 2, days: [3, 4] }] },
            { id: "home", label: "Whole home", note: "2,000 sq ft", days: [5, 7], crew: [
                { role: "painter", workers: 3, days: [5, 7] }] },
        ],
    },
    {
        id: "bathroom", scale: "small", category: "Repairs & renovation", name: "Bathroom refresh",
        description: "New fixtures, vanity and finishes in the existing layout.",
        icon: "M6 26h36v6a8 8 0 0 1-8 8H14a8 8 0 0 1-8-8zM10 26V10a4 4 0 0 1 8 0M14 40v4M34 40v4",
        sizes: [
            { id: "half", label: "Half bath", note: "Toilet and sink", days: [4, 6], crew: [
                { role: "plumber", workers: 1, days: [1, 2] }, { role: "carpenter", workers: 1, days: [2, 3] },
                { role: "painter", workers: 1, days: [1, 2] }, { role: "general", workers: 1, days: [2, 3] }] },
            { id: "full", label: "Full bath", note: "With shower or tub", typical: true, days: [8, 12], crew: [
                { role: "plumber", workers: 1, days: [2, 3] }, { role: "electrician", workers: 1, days: [1, 2] },
                { role: "carpenter", workers: 2, days: [4, 6] }, { role: "painter", workers: 1, days: [2, 3] },
                { role: "general", workers: 1, days: [3, 5] }] },
        ],
    },
    {
        id: "addition", scale: "medium", category: "Additions & remodels", name: "Home addition",
        description: "Framed addition tied into the existing house, with power and plumbing.",
        icon: "M4 40V20L18 10l14 10v20zM32 40V26h12v14M32 26l6-4 6 4M12 40V30h8v10",
        sizes: [
            { id: "room", label: "Single room", note: "About 250 sq ft", typical: true, days: [17, 22], crew: [
                { role: "carpenter", workers: 3, days: [12, 15] }, { role: "electrician", workers: 2, days: [3, 4] },
                { role: "plumber", workers: 1, days: [2, 3] }, { role: "general", workers: 2, days: [17, 22] }] },
            { id: "suite", label: "Two rooms", note: "About 500 sq ft", days: [30, 40], crew: [
                { role: "mason", workers: 3, days: [4, 6] }, { role: "carpenter", workers: 4, days: [18, 24] },
                { role: "roofer", workers: 3, days: [3, 4] }, { role: "electrician", workers: 2, days: [5, 7] },
                { role: "plumber", workers: 2, days: [4, 5] }, { role: "general", workers: 2, days: [30, 40] }] },
        ],
    },
    {
        id: "kitchen", scale: "medium", category: "Additions & remodels", name: "Kitchen remodel",
        description: "New cabinets, counters and appliances, from a cosmetic update to a full gut.",
        icon: "M4 22h40v20H4zM4 22l4-8h32l4 8M12 28h8v8h-8zM28 28h8M28 34h8",
        sizes: [
            { id: "update", label: "Cosmetic update", note: "Same layout", days: [10, 14], crew: [
                { role: "carpenter", workers: 2, days: [6, 8] }, { role: "electrician", workers: 1, days: [2, 3] },
                { role: "plumber", workers: 1, days: [2, 3] }, { role: "painter", workers: 1, days: [2, 3] }] },
            { id: "gut", label: "Full remodel", note: "Down to the studs", typical: true, days: [25, 35], crew: [
                { role: "general", workers: 2, days: [5, 7] }, { role: "carpenter", workers: 3, days: [12, 16] },
                { role: "electrician", workers: 2, days: [5, 7] }, { role: "plumber", workers: 1, days: [4, 6] },
                { role: "drywall", workers: 2, days: [4, 6] }, { role: "painter", workers: 1, days: [3, 4] }] },
        ],
    },
    {
        id: "roof", scale: "medium", category: "Roofing & foundations", name: "Roof replacement",
        description: "Tear off the old roof, repair decking and install new shingles.",
        icon: "M2 30L24 10l22 20M8 25v15h32V25M12 30h24M16 35h16",
        sizes: [
            { id: "1500", label: "1,500 sq ft", note: "Ranch home", typical: true, days: [3, 5], crew: [
                { role: "roofer", workers: 4, days: [3, 5] }, { role: "general", workers: 2, days: [3, 5] }] },
            { id: "3000", label: "3,000 sq ft", note: "Two-storey home", days: [6, 9], crew: [
                { role: "roofer", workers: 6, days: [6, 9] }, { role: "general", workers: 2, days: [6, 9] }] },
        ],
    },
    {
        id: "foundation", scale: "medium", category: "Roofing & foundations", name: "Foundation & slab",
        description: "Excavate, form and pour a concrete foundation or slab.",
        icon: "M4 24h40v8H4zM4 32v8h40v-8M12 24v16M24 24v16M36 24v16M10 18h28",
        sizes: [
            { id: "garage", label: "Garage slab", note: "About 600 sq ft", days: [4, 6], crew: [
                { role: "operator", workers: 1, days: [1, 2] }, { role: "mason", workers: 3, days: [3, 4] },
                { role: "general", workers: 2, days: [4, 6] }] },
            { id: "house", label: "House foundation", note: "Full basement walls", typical: true, days: [10, 15], crew: [
                { role: "operator", workers: 1, days: [3, 4] }, { role: "mason", workers: 5, days: [8, 12] },
                { role: "general", workers: 3, days: [10, 15] }] },
        ],
    },
    {
        id: "home", scale: "medium", category: "New homes", name: "Single-family home",
        description: "New house from foundation to finished interior, with all main trades.",
        icon: "M6 40V20L24 6l18 14v20zM18 40V28h12v12M10 24h6v6h-6zM32 24h6v6h-6z",
        sizes: [
            { id: "1800", label: "1,800 sq ft", note: "Single storey", typical: true, days: [90, 120], crew: [
                { role: "supervisor", workers: 1, days: [90, 120] }, { role: "operator", workers: 1, days: [5, 8] },
                { role: "mason", workers: 4, days: [10, 14] }, { role: "carpenter", workers: 5, days: [35, 45] },
                { role: "roofer", workers: 4, days: [5, 7] }, { role: "electrician", workers: 2, days: [12, 16] },
                { role: "plumber", workers: 2, days: [10, 14] }, { role: "hvac", workers: 2, days: [8, 10] },
                { role: "drywall", workers: 3, days: [10, 14] }, { role: "painter", workers: 2, days: [8, 10] },
                { role: "general", workers: 3, days: [60, 80] }] },
            { id: "2800", label: "2,800 sq ft", note: "Two storey", days: [120, 160], crew: [
                { role: "supervisor", workers: 1, days: [120, 160] }, { role: "operator", workers: 1, days: [6, 10] },
                { role: "mason", workers: 5, days: [12, 16] }, { role: "carpenter", workers: 6, days: [45, 60] },
                { role: "roofer", workers: 5, days: [6, 9] }, { role: "electrician", workers: 3, days: [15, 20] },
                { role: "plumber", workers: 2, days: [14, 18] }, { role: "hvac", workers: 2, days: [10, 14] },
                { role: "drywall", workers: 4, days: [12, 16] }, { role: "painter", workers: 3, days: [10, 12] },
                { role: "general", workers: 4, days: [80, 110] }] },
        ],
    },
    {
        id: "office", scale: "large", category: "Commercial buildings", name: "Office building",
        description: "Steel-frame office building with core services and open-plan floors.",
        icon: "M10 44V6h28v38M16 12h4v4h-4zM28 12h4v4h-4zM16 22h4v4h-4zM28 22h4v4h-4zM16 32h4v4h-4zM28 32h4v4h-4zM20 44v-6h8v6",
        sizes: [
            { id: "2storey", label: "2 storeys", note: "About 10,000 sq ft", typical: true, days: [160, 210], crew: [
                { role: "supervisor", workers: 2, days: [160, 210] }, { role: "operator", workers: 3, days: [20, 30] },
                { role: "mason", workers: 8, days: [30, 40] }, { role: "ironworker", workers: 8, days: [25, 35] },
                { role: "carpenter", workers: 6, days: [40, 55] }, { role: "electrician", workers: 5, days: [50, 65] },
                { role: "plumber", workers: 3, days: [35, 45] }, { role: "hvac", workers: 4, days: [35, 45] },
                { role: "drywall", workers: 6, days: [25, 35] }, { role: "general", workers: 8, days: [140, 180] }] },
            { id: "4storey", label: "4 storeys", note: "About 40,000 sq ft", days: [280, 360], crew: [
                { role: "supervisor", workers: 3, days: [280, 360] }, { role: "operator", workers: 5, days: [40, 55] },
                { role: "mason", workers: 14, days: [50, 65] }, { role: "ironworker", workers: 16, days: [45, 60] },
                { role: "carpenter", workers: 10, days: [70, 90] }, { role: "electrician", workers: 10, days: [90, 120] },
                { role: "plumber", workers: 6, days: [60, 80] }, { role: "hvac", workers: 8, days: [60, 80] },
                { role: "drywall", workers: 12, days: [40, 55] }, { role: "general", workers: 14, days: [240, 310] }] },
        ],
    },
    {
        id: "retail", scale: "large", category: "Commercial buildings", name: "Retail building",
        description: "Single-storey retail shell with storefront glazing and rooftop units.",
        icon: "M4 44V18h40v26M4 18l4-10h32l4 10M10 26h28v10H10zM20 44v-8h8v8",
        sizes: [
            { id: "single", label: "Single tenant", note: "About 5,000 sq ft", typical: true, days: [90, 120], crew: [
                { role: "supervisor", workers: 1, days: [90, 120] }, { role: "operator", workers: 2, days: [10, 15] },
                { role: "mason", workers: 6, days: [20, 28] }, { role: "ironworker", workers: 5, days: [12, 16] },
                { role: "carpenter", workers: 4, days: [25, 35] }, { role: "roofer", workers: 4, days: [8, 12] },
                { role: "electrician", workers: 3, days: [25, 35] }, { role: "plumber", workers: 2, days: [15, 20] },
                { role: "hvac", workers: 2, days: [12, 16] }, { role: "general", workers: 5, days: [75, 100] }] },
            { id: "strip", label: "Strip center", note: "About 20,000 sq ft", days: [160, 210], crew: [
                { role: "supervisor", workers: 2, days: [160, 210] }, { role: "operator", workers: 3, days: [20, 30] },
                { role: "mason", workers: 10, days: [35, 45] }, { role: "ironworker", workers: 8, days: [25, 35] },
                { role: "carpenter", workers: 6, days: [45, 60] }, { role: "roofer", workers: 6, days: [15, 20] },
                { role: "electrician", workers: 5, days: [45, 60] }, { role: "plumber", workers: 3, days: [30, 40] },
                { role: "hvac", workers: 4, days: [25, 35] }, { role: "general", workers: 8, days: [140, 180] }] },
        ],
    },
    {
        id: "warehouse", scale: "large", category: "Industrial facilities", name: "Warehouse",
        description: "Pre-engineered steel warehouse on a slab, with loading docks.",
        icon: "M2 44V20L24 8l22 12v24M8 44V30h10v14M22 44V30h10v14M36 30h6v6h-6z",
        sizes: [
            { id: "small", label: "Small", note: "About 20,000 sq ft", days: [90, 120], crew: [
                { role: "supervisor", workers: 1, days: [90, 120] }, { role: "operator", workers: 2, days: [15, 20] },
                { role: "mason", workers: 8, days: [20, 28] }, { role: "ironworker", workers: 6, days: [18, 24] },
                { role: "roofer", workers: 4, days: [10, 14] }, { role: "electrician", workers: 3, days: [25, 35] },
                { role: "plumber", workers: 2, days: [10, 15] }, { role: "general", workers: 6, days: [75, 100] }] },
            { id: "medium", label: "Medium", note: "About 60,000 sq ft", typical: true, days: [140, 180], crew: [
                { role: "supervisor", workers: 2, days: [140, 180] }, { role: "operator", workers: 4, days: [25, 35] },
                { role: "mason", workers: 12, days: [40, 55] }, { role: "ironworker", workers: 10, days: [30, 40] },
                { role: "roofer", workers: 6, days: [15, 20] }, { role: "electrician", workers: 6, days: [45, 60] },
                { role: "plumber", workers: 3, days: [25, 35] }, { role: "hvac", workers: 4, days: [25, 35] },
                { role: "general", workers: 10, days: [120, 160] }] },
            { id: "large", label: "Large", note: "About 150,000 sq ft", days: [200, 260], crew: [
                { role: "supervisor", workers: 3, days: [200, 260] }, { role: "operator", workers: 6, days: [40, 55] },
                { role: "mason", workers: 20, days: [60, 80] }, { role: "ironworker", workers: 16, days: [50, 65] },
                { role: "roofer", workers: 10, days: [25, 35] }, { role: "electrician", workers: 10, days: [70, 90] },
                { role: "plumber", workers: 5, days: [40, 55] }, { role: "hvac", workers: 6, days: [40, 55] },
                { role: "general", workers: 16, days: [170, 220] }] },
        ],
    },
    {
        id: "industrial", scale: "large", category: "Industrial facilities", name: "Light industrial plant",
        description: "Production building with heavy power, process piping and ventilation.",
        icon: "M2 44V24l10-6v6l10-6v6l10-6v26M36 44V8h6v36M8 32h6v6H8zM20 32h6v6h-6z",
        sizes: [
            { id: "40000", label: "40,000 sq ft", note: "Single line", typical: true, days: [180, 240], crew: [
                { role: "supervisor", workers: 2, days: [180, 240] }, { role: "operator", workers: 4, days: [25, 35] },
                { role: "mason", workers: 12, days: [40, 55] }, { role: "ironworker", workers: 10, days: [35, 45] },
                { role: "roofer", workers: 6, days: [15, 20] }, { role: "electrician", workers: 8, days: [70, 90] },
                { role: "plumber", workers: 5, days: [50, 65] }, { role: "hvac", workers: 6, days: [45, 60] },
                { role: "general", workers: 10, days: [150, 200] }] },
        ],
    },
];

const SCALE_NAMES = { small: "Small projects", medium: "Medium projects", large: "Large projects" };

const groupsBox = document.getElementById("project-groups");
const sizeBox = document.getElementById("size-options");
const HOURS_PER_DAY = PAGE_DATA.hoursPerDay;
const customCard = document.getElementById("custom-crew-option");
const customRoles = document.getElementById("custom-roles");
const customDays = document.getElementById("custom-days");
const customWorkers = {};
const customCurrency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

const state = {
    scale: "small",
    project: null,     // one entry from PROJECTS
    sizeId: null,
};

function money(value) {
    // round to the nearest $100 so the estimate does not look more exact than it is
    return "$" + (Math.round(value / 100) * 100).toLocaleString();
}

function range(low, high, unit) {
    return low === high ? low.toLocaleString() + " " + unit : low.toLocaleString() + "–" + high.toLocaleString() + " " + unit;
}

function plural(count, word) {
    return count.toLocaleString() + " " + word + (count === 1 ? "" : "s");
}

function currentSize() {
    return state.project.sizes.find((size) => size.id === state.sizeId);
}

// Keep the choice in the address bar so a refresh or shared link opens the same estimate.
// project_id (a saved project the crew is being chosen for) is kept as well.
function updateAddress(params) {
    const projectId = new URLSearchParams(location.search).get("project_id");
    if (projectId) params.set("project_id", projectId);
    history.replaceState(null, "", "?" + params + location.hash);
}

// The labor calculation (services/crews.py does the same for saved projects)
// cost = workers × hourly rate × hours per day × days on site
function estimate(size) {
    const rows = [];
    let workers = 0;
    let hourly = 0;
    let low = 0;
    let high = 0;
    for (const member of size.crew) {
        const specialty = RATES[member.role];
        const memberHourly = member.workers * specialty.rate;
        const row = {
            name: specialty.name,
            workers: member.workers,
            rate: specialty.rate,
            hourly: memberHourly,
            days: member.days,
            low: memberHourly * HOURS_PER_DAY * member.days[0],
            high: memberHourly * HOURS_PER_DAY * member.days[1],
        };
        rows.push(row);
        workers += row.workers;
        hourly += row.hourly;
        low += row.low;
        high += row.high;
    }
    return { rows: rows, workers: workers, hourly: hourly, low: low, high: high };
}

function showProjects() {
    groupsBox.textContent = "";
    const projects = [];
    const categories = [];
    for (const project of PROJECTS) {
        if (project.scale !== state.scale) continue;
        projects.push(project);
        if (!categories.includes(project.category)) {
            categories.push(project.category);
        }
    }

    for (const category of categories) {
        const group = document.createElement("div");
        group.className = "project-group";
        const heading = document.createElement("h3");
        heading.textContent = category;
        const list = document.createElement("div");
        list.className = "project-list";

        for (const project of projects) {
            if (project.category !== category) continue;
            const typical = project.sizes.find((size) => size.typical) || project.sizes[0];
            const card = document.createElement("button");
            card.type = "button";
            card.className = "project-card";
            card.dataset.project = project.id;
            card.setAttribute("aria-pressed", String(state.project === project));
            card.innerHTML = '<svg class="project-icon" viewBox="0 0 48 48" aria-hidden="true" focusable="false"><path></path></svg>' +
                '<span class="project-text"><strong></strong><span class="project-desc"></span>' +
                '<span class="project-meta"></span></span><span class="arrow" aria-hidden="true">&rarr;</span>';
            card.querySelector("path").setAttribute("d", project.icon);
            card.querySelector("strong").textContent = project.name;
            card.querySelector(".project-desc").textContent = project.description;
            card.querySelector(".project-meta").textContent =
                plural(project.sizes.length, "size") + " · typically " + range(typical.days[0], typical.days[1], "days");
            card.addEventListener("click", function () { chooseProject(project, null, true); });
            list.appendChild(card);
        }
        group.append(heading, list);
        groupsBox.appendChild(group);
    }
}

function chooseProject(project, sizeId, scrollToResult) {
    state.project = project;
    customCard.setAttribute("aria-pressed", "false");
    document.getElementById("custom-builder").hidden = true;
    const typical = project.sizes.find((size) => size.typical) || project.sizes[0];
    state.sizeId = project.sizes.some((size) => size.id === sizeId) ? sizeId : typical.id;
    document.querySelectorAll(".project-card").forEach(function (card) {
        card.setAttribute("aria-pressed", String(card.dataset.project === project.id));
    });
    buildSizeOptions();
    showEstimate();

    if (scrollToResult) {
        const section = document.getElementById("estimate");
        section.scrollIntoView({ behavior: "smooth", block: "start" });
        section.focus({ preventScroll: true });
    }
}

function buildSizeOptions() {
    sizeBox.textContent = "";
    state.project.sizes.forEach(function (size) {
        const label = document.createElement("label");
        label.className = "size-option";
        label.innerHTML = '<input type="radio" name="size"><span><strong></strong><small></small></span>';
        const input = label.querySelector("input");
        input.value = size.id;
        input.checked = size.id === state.sizeId;
        label.querySelector("strong").textContent = size.label;
        label.querySelector("small").textContent = size.note;
        input.addEventListener("change", function () {
            state.sizeId = size.id;
            showEstimate();
        });
        sizeBox.appendChild(label);
    });
}

function showEstimate() {
    const project = state.project;
    const size = currentSize();
    const result = estimate(size);

    document.getElementById("estimate-empty").hidden = true;
    document.getElementById("estimate-result").hidden = false;
    document.getElementById("quote-status").hidden = true;

    document.getElementById("path-scale").textContent = SCALE_NAMES[project.scale];
    document.getElementById("path-category").textContent = project.category;
    document.getElementById("path-project").textContent = project.name + " · " + size.label;
    document.getElementById("result-name").textContent = project.name;
    document.getElementById("result-description").textContent = project.description;

    document.getElementById("result-cost").textContent = money(result.low) + " – " + money(result.high);
    document.getElementById("result-days").textContent = range(size.days[0], size.days[1], "working days");
    document.getElementById("result-crew").textContent =
        plural(result.workers, "worker") + " across " + result.rows.length + (result.rows.length === 1 ? " specialty" : " specialties");
    document.getElementById("result-hourly").textContent = "$" + result.hourly.toLocaleString() + " / hr";
    document.getElementById("result-hours").textContent = HOURS_PER_DAY + " hours";

    const body = document.getElementById("crew-rows");
    body.textContent = "";
    const longest = size.days[1];
    result.rows.forEach(function (row) {
        const tr = document.createElement("tr");
        tr.innerHTML = '<th scope="row"><span class="role-name"></span><span class="worker-dots" aria-hidden="true"></span></th>' +
            '<td class="num"></td><td class="num"></td><td class="num"></td>' +
            '<td><span class="days-text"></span><span class="days-bar" aria-hidden="true"><span></span></span></td><td class="num cost"></td>';
        tr.querySelector(".role-name").textContent = row.name;
        const dots = tr.querySelector(".worker-dots");
        for (let i = 0; i < Math.min(row.workers, 12); i++) dots.appendChild(document.createElement("i"));
        if (row.workers > 12) dots.append("+" + (row.workers - 12));
        const cells = tr.querySelectorAll("td");
        cells[0].textContent = row.workers;
        cells[1].textContent = "$" + row.rate;
        cells[2].textContent = "$" + row.hourly.toLocaleString();
        tr.querySelector(".days-text").textContent = range(row.days[0], row.days[1], "days");
        tr.querySelector(".days-bar span").style.width = (row.days[1] / longest * 100) + "%";
        cells[4].textContent = money(row.low) + " – " + money(row.high);
        body.appendChild(tr);
    });
    document.getElementById("total-workers").textContent = result.workers;
    document.getElementById("total-hourly").textContent = "$" + result.hourly.toLocaleString();
    document.getElementById("total-days").textContent = range(size.days[0], size.days[1], "days");
    document.getElementById("total-cost").textContent = money(result.low) + " – " + money(result.high);

    updateAddress(new URLSearchParams({ project: project.id, size: size.id }));
    showSaveCrewForm();
}

function customDayCount() {
    const enteredDays = Number(customDays.value);
    if (customDays.value === "" || !Number.isSafeInteger(enteredDays) || enteredDays < 1) {
        return 1;
    }
    return enteredDays;
}

// Custom Crew uses the same specialty rates and eight-hour work day as the presets.
function showCustomEstimate() {
    const days = customDayCount();
    let workers = 0;
    let hourly = 0;

    for (const row of customRoles.children) {
        const role = row.dataset.role;
        const count = customWorkers[role];
        const rate = RATES[role].rate;
        workers += count;
        hourly += count * rate;
        row.querySelector(".custom-count").textContent = count;
        row.querySelector(".custom-role-cost").textContent = customCurrency.format(count * rate * HOURS_PER_DAY * days);
        row.querySelector('[data-change="-1"]').disabled = count === 0;
        row.querySelector('[data-change="1"]').disabled = count === 99;
    }

    document.getElementById("custom-total-workers").textContent = workers;
    document.getElementById("custom-total-days").textContent = days;
    document.getElementById("custom-total-hourly").textContent = customCurrency.format(hourly);
    document.getElementById("custom-total-cost").textContent = customCurrency.format(hourly * HOURS_PER_DAY * days);
}

function chooseCustomCrew(scrollToResult) {
    state.project = null;
    state.sizeId = null;
    document.querySelectorAll(".project-card").forEach(function (card) {
        card.setAttribute("aria-pressed", String(card === customCard));
    });
    document.getElementById("estimate-empty").hidden = true;
    document.getElementById("estimate-result").hidden = true;
    document.getElementById("custom-builder").hidden = false;
    showCustomEstimate();
    updateAddress(new URLSearchParams({ crew: "custom" }));
    showSaveCrewForm();

    if (scrollToResult) {
        const section = document.getElementById("estimate");
        section.scrollIntoView({ behavior: "smooth", block: "start" });
        section.focus({ preventScroll: true });
    }
}

for (const [role, specialty] of Object.entries(RATES)) {
    customWorkers[role] = 0;
    const row = document.createElement("div");
    row.className = "custom-role";
    row.dataset.role = role;
    row.innerHTML = '<div class="custom-role-info"><strong class="role-name"></strong><span class="custom-rate"></span></div>' +
        '<div class="custom-counter"><button type="button" data-change="-1">−</button><span class="custom-count">0</span><button type="button" data-change="1">+</button></div>' +
        '<div class="custom-role-cost">$0.00</div>';
    row.querySelector(".role-name").textContent = specialty.name;
    row.querySelector(".custom-rate").textContent = customCurrency.format(specialty.rate) + " / hr";
    row.querySelector('[data-change="-1"]').setAttribute("aria-label", "Decrease " + specialty.name + " workers");
    row.querySelector('[data-change="1"]').setAttribute("aria-label", "Increase " + specialty.name + " workers");
    customRoles.appendChild(row);
}

customCard.addEventListener("click", function () { chooseCustomCrew(true); });
customRoles.addEventListener("click", function (event) {
    const button = event.target.closest("button[data-change]");
    if (!button) return;
    const role = button.closest(".custom-role").dataset.role;
    const count = customWorkers[role] + Number(button.dataset.change);
    if (count < 0 || count > 99) return;
    customWorkers[role] = count;
    showCustomEstimate();
});
customDays.addEventListener("input", showCustomEstimate);
customDays.addEventListener("change", function () {
    customDays.value = customDayCount();
    showCustomEstimate();
});
document.getElementById("custom-reset").addEventListener("click", function () {
    for (const role of Object.keys(customWorkers)) customWorkers[role] = 0;
    customDays.value = 1;
    showCustomEstimate();
});
showCustomEstimate();

const saveCrewForm = document.getElementById("save-crew-form");

function showSaveCrewForm() {
    if (saveCrewForm) saveCrewForm.hidden = false;
}

// The crew on screen, in the format services/crews.py saves:
// a label, the project's [shortest, longest] days, and each specialty's workers and days.
function currentCrew() {
    if (state.project) {
        const size = currentSize();
        const members = [];
        for (const member of size.crew) {
            members.push({ role: member.role, workers: member.workers, days: member.days });
        }
        return {
            source: "preset", preset: state.project.id, size: size.id,
            label: state.project.name + " · " + size.label, days: size.days, members: members,
        };
    }
    const days = customDayCount();
    const members = [];
    for (const role of Object.keys(customWorkers)) {
        if (customWorkers[role] > 0) {
            members.push({ role: role, workers: customWorkers[role], days: [days, days] });
        }
    }
    return { source: "custom", label: "Custom crew", days: [days, days], members: members };
}

if (saveCrewForm) {
    saveCrewForm.addEventListener("submit", function (event) {
        const crew = currentCrew();
        const status = document.getElementById("save-crew-status");
        if (crew.members.length === 0) {
            event.preventDefault();
            status.textContent = "Add at least one worker before saving the crew.";
            status.hidden = false;
            return;
        }
        document.getElementById("crew-input").value = JSON.stringify(crew);
        saveCrewForm.querySelector("button[type=submit]").disabled = true;
    });
}

function loadSavedCustomCrew() {
    const saved = PAGE_DATA.savedCrew;
    if (!saved || saved.source !== "custom") return;
    for (const member of saved.members) {
        if (member.role in customWorkers) customWorkers[member.role] = member.workers;
    }
    customDays.value = saved.days[0];
}

document.getElementById("quote-button").addEventListener("click", function () {
    // Sending needs services/rentals.request_crew, which is still a stub, so nothing leaves the browser.
    const status = document.getElementById("quote-status");
    status.textContent = "Quote requests are unavailable. Nothing was sent.";
    status.hidden = false;
});

document.querySelectorAll('input[name="scale"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
        state.scale = radio.value;
        showProjects();
    });
});

const params = new URLSearchParams(location.search);
const startProject = PROJECTS.find((project) => project.id === params.get("project"));
if (startProject) {
    state.scale = startProject.scale;
    document.querySelector(`input[name="scale"][value="${startProject.scale}"]`).checked = true;
}
showProjects();
if (params.get("crew") === "custom") {
    loadSavedCustomCrew();
    chooseCustomCrew(false);
}
else if (startProject) chooseProject(startProject, params.get("size"), false);
