const activeCharts = new Set();

function normalizeChartSpec(spec, rows) {
    const normalized = { ...spec };

    if (
        normalized.type !== "bar" ||
        !Array.isArray(rows) ||
        rows.length === 0
    ) {
        return normalized;
    }

    const firstRow = rows[0];

    if (
        !Object.hasOwn(firstRow, normalized.x) ||
        !Object.hasOwn(firstRow, normalized.y)
    ) {
        return normalized;
    }

    const xIsNumeric = rows.some(
        row => isFiniteNumber(row[normalized.x])
    );

    const yIsNumeric = rows.some(
        row => isFiniteNumber(row[normalized.y])
    );

    // The agent supplied metric as x and category as y.
    if (xIsNumeric && !yIsNumeric) {
        [normalized.x, normalized.y] = [
            normalized.y,
            normalized.x
        ];
    }

    return normalized;
}

function renderVisualizationsInto(container, specs, evidence) {
    destroyChartsInside(container);
    container.innerHTML = "";

    if (!Array.isArray(specs) || !specs.length) return;

    const evidenceMap = new Map(
        (evidence || []).map(item => [item.id, item])
    );

    const renderable = specs
    .map(spec => {
        const data = parseEvidenceRows(
            evidenceMap.get(spec.evidence)?.result
        );

        return {
            spec: normalizeChartSpec(spec, data),
            data
        };
    })
    .filter(item => item.data.length);

    container.classList.toggle(
        "single-chart",
        renderable.length === 1
    );

    // console.log("FINAL CHART SPEC:", JSON.stringify(spec));
    renderable.forEach(({spec, data}) => {
        
        console.log("FINAL CHART SPEC:", JSON.stringify(spec));

        const card = document.createElement("article");
        card.className = "chart-card";

        const heading = document.createElement("div");
        heading.className = "chart-heading";

        const title = document.createElement("h3");
        title.textContent = normalizeChartTitle(spec.title);

        const source = document.createElement("p");
        source.textContent =
            `Grounded in ${spec.evidence || ""}`;

        heading.append(title, source);

        const canvasWrap =
            document.createElement("div");

        canvasWrap.className =
            "chart-canvas-wrap";

        /*
        * Keep final charts at a stable height.
        *
        * Chart.js is responsive and uses
        * maintainAspectRatio:false, so the parent
        * container must have an explicit height.
        * Otherwise opening/closing sections below
        * the chart can cause it to grow vertically.
        */
        canvasWrap.style.height =
            "360px";

        canvasWrap.style.position =
            "relative";

        const canvas =
            document.createElement("canvas");

        canvasWrap.appendChild(canvas);

        card.append(
            heading,
            canvasWrap
        );

        container.appendChild(card);

        const chart = new Chart(
            canvas.getContext("2d"),
            buildChartConfig(spec, data)
        );

        activeCharts.add(chart);
    });
}


function destroyChartsInside(container) {
    [...activeCharts].forEach(chart => {

        const canvas = chart.canvas;

        if (
            canvas &&
            container.contains(canvas)
        ) {
            chart.destroy();
            activeCharts.delete(chart);
        }
    });
}


function parseEvidenceRows(raw) {

    if (Array.isArray(raw)) {
        return raw;
    }

    if (
        raw &&
        typeof raw === "object"
    ) {
        if (Array.isArray(raw.rows)) {
            return raw.rows;
        }

        if (Array.isArray(raw.data)) {
            return raw.data;
        }
    }

    if (typeof raw !== "string") {
        return [];
    }

    const text = raw.trim();

    try {
        const parsed = JSON.parse(text);

        if (Array.isArray(parsed)) {
            return parsed;
        }

        if (Array.isArray(parsed?.rows)) {
            return parsed.rows;
        }

        if (Array.isArray(parsed?.data)) {
            return parsed.data;
        }

    } catch {}


    /*
     * PG Airman may return Python-style
     * representations such as:
     *
     * Decimal('20.92')
     *
     * Repair them before trying JSON again.
     */

    const repaired = text
        .replace(
            /Decimal\('([^']+)'\)/g,
            "$1"
        )
        .replace(/\bNone\b/g, "null")
        .replace(/\bTrue\b/g, "true")
        .replace(/\bFalse\b/g, "false")
        .replace(/'/g, '"');

    try {
        const parsed =
            JSON.parse(repaired);

        if (Array.isArray(parsed)) {
            return parsed;
        }

        if (Array.isArray(parsed?.rows)) {
            return parsed.rows;
        }

        if (Array.isArray(parsed?.data)) {
            return parsed.data;
        }

    } catch {}

    return [];
}



// ============================================================
// FINAL VISUALIZATION CONFIGURATION
// ============================================================

function buildChartConfig(
    spec,
    sourceRows
) {

    const rows =
        prepareRows(
            spec,
            sourceRows
        );

    if (spec.type === "pie") {
        return buildPieConfig(
            spec,
            rows
        );
    }

    if (spec.type === "scatter") {
        return buildScatterConfig(
            spec,
            rows
        );
    }

    if (spec.type === "combo") {
        return buildComboConfig(
            spec,
            rows
        );
    }

    return buildCartesianConfig(
        spec,
        rows
    );
}


function prepareRows(
    spec,
    rows
) {

    const copy = [...rows];

    /*
     * Categorical bar charts are ranked
     * automatically.
     */

    if (
        spec.type === "bar" &&
        spec.y
    ) {
        copy.sort(
            (a, b) =>
                numberValue(b[spec.y]) -
                numberValue(a[spec.y])
        );
    }

    return copy;
}


function buildCartesianConfig(
    spec,
    rows
) {

    const labels =
        rows.map(
            row =>
                String(row[spec.x])
        );

    const values =
        rows.map(
            row =>
                numberValue(
                    row[spec.y]
                )
        );

    const isBar =
        spec.type === "bar";

    return {
        type:
            isBar
                ? "bar"
                : "line",

        data: {
            labels,

            datasets: [{
                label:
                    humanize(spec.y),

                data: values,

                borderWidth:
                    isBar ? 0 : 3,

                borderRadius:
                    isBar ? 7 : 0,

                pointRadius:
                    isBar ? 0 : 4,

                pointHoverRadius:
                    isBar ? 0 : 6,

                tension:
                    isBar ? 0 : 0.28,

                fill: false,

                backgroundColor:
                    categoryColors(
                        values.length
                    ),

                borderColor:
                    "#4f46e5"
            }]
        },

        options:
            commonOptions(
                spec,
                {
                    /*
                     * Six or more categories:
                     * horizontal bars.
                     */
                    indexAxis:
                        isBar &&
                        labels.length >= 6
                            ? "y"
                            : "x"
                }
            )
    };
}


function buildPieConfig(
    spec,
    rows
) {

    return {
        type: "doughnut",

        data: {

            labels:
                rows.map(
                    row =>
                        String(
                            row[spec.x]
                        )
                ),

            datasets: [{
                label:
                    humanize(
                        spec.y
                    ),

                data:
                    rows.map(
                        row =>
                            numberValue(
                                row[spec.y]
                            )
                    ),

                backgroundColor:
                    categoryColors(
                        rows.length
                    ),

                borderColor:
                    "#ffffff",

                borderWidth: 2,

                hoverOffset: 8
            }]
        },

        options:
            commonOptions(
                spec,
                {
                    cutout: "52%",
                    scales: undefined
                }
            )
    };
}


function buildScatterConfig(
    spec,
    rows
) {

    return {
        type: "scatter",

        data: {
            datasets: [{
                label:
                    spec.title ||
                    `${humanize(spec.x)} vs ${humanize(spec.y)}`,

                data:
                    rows.map(
                        row => ({
                            x:
                                numberValue(
                                    row[spec.x]
                                ),

                            y:
                                numberValue(
                                    row[spec.y]
                                )
                        })
                    ),

                pointRadius: 5,

                pointHoverRadius: 8,

                backgroundColor:
                    "rgba(79, 70, 229, 0.70)"
            }]
        },

        options:
            commonOptions(spec)
    };
}


function buildComboConfig(
    spec,
    rows
) {

    const labels =
        rows.map(
            row =>
                String(row[spec.x])
        );

    const colors =
        categoryColors(
            Math.max(
                spec.series?.length || 0,
                2
            )
        );

    const datasets =
        (spec.series || [])
            .map(
                (series, index) => ({
                    type:
                        series.type === "line"
                            ? "line"
                            : "bar",

                    label:
                        series.label ||
                        humanize(
                            series.field
                        ),

                    data:
                        rows.map(
                            row =>
                                numberValue(
                                    row[
                                        series.field
                                    ]
                                )
                        ),

                    yAxisID:
                        series.axis === "right"
                            ? "y1"
                            : "y",

                    backgroundColor:
                        colors[index],

                    borderColor:
                        colors[index],

                    borderWidth:
                        series.type === "line"
                            ? 3
                            : 0,

                    borderRadius:
                        series.type === "bar"
                            ? 7
                            : 0,

                    tension: 0.28,

                    pointRadius:
                        series.type === "line"
                            ? 4
                            : 0,

                    pointHoverRadius:
                        series.type === "line"
                            ? 6
                            : 0
                })
            );

    return {
        type: "bar",

        data: {
            labels,
            datasets
        },

        options:
            commonOptions(
                spec,
                {
                    scales: {

                        x:
                            axisX(),

                        y:
                            axisY("left"),

                        y1: {
                            ...axisY(
                                "right"
                            ),

                            position:
                                "right",

                            grid: {
                                drawOnChartArea:
                                    false
                            }
                        }
                    }
                }
            )
    };
}


function commonOptions(
    spec,
    overrides = {}
) {

    const defaultScales = {
        x: axisX(),
        y: axisY()
    };

    return {
        responsive: true,

        maintainAspectRatio:
            false,

        interaction: {
            mode: "nearest",
            intersect: false
        },

        animation: {
            duration: 650
        },

        plugins: {

            legend: {
                display:
                    spec.type === "pie" ||
                    spec.type === "combo",

                position:
                    "bottom",

                labels: {
                    usePointStyle:
                        true,

                    boxWidth: 8,

                    padding: 18,

                    color:
                        "#475569",

                    font: {
                        family:
                            "Inter",

                        size: 11
                    }
                }
            },

            tooltip: {
                enabled: true,

                backgroundColor:
                    "#0f172a",

                titleColor:
                    "#ffffff",

                bodyColor:
                    "#e2e8f0",

                padding: 11,

                cornerRadius: 9,

                displayColors:
                    true
            }
        },

        scales:
            overrides.scales === undefined &&
            spec.type !== "pie"
                ? defaultScales
                : overrides.scales,

        ...overrides
    };
}


function axisX() {
    return {
        grid: {
            display: false
        },

        ticks: {
            color:
                "#64748b",

            font: {
                family:
                    "Inter",

                size: 10
            },

            maxRotation: 30,
            minRotation: 0
        },

        border: {
            color:
                "#cbd5e1"
        }
    };
}


function axisY(
    position = "left"
) {

    return {
        beginAtZero: true,

        position,

        grid: {
            color:
                "rgba(226,232,240,.75)"
        },

        ticks: {
            color:
                "#64748b",

            font: {
                family:
                    "Inter",

                size: 10
            }
        },

        border: {
            display: false
        }
    };
}


function categoryColors(count) {

    const palette = [
        "#4f46e5",
        "#06b6d4",
        "#8b5cf6",
        "#10b981",
        "#f59e0b",
        "#ec4899",
        "#3b82f6",
        "#84cc16",
        "#f97316",
        "#14b8a6"
    ];

    return Array.from(
        {
            length: count
        },

        (_, index) =>
            palette[
                index %
                palette.length
            ]
    );
}


function numberValue(value) {

    const number =
        Number(value);

    return Number.isFinite(number)
        ? number
        : 0;
}


function humanize(value) {

    return String(
        value || ""
    )
        .replace(
            /_/g,
            " "
        )
        .replace(
            /\b\w/g,
            char =>
                char.toUpperCase()
        );
}


// ============================================================
// PROGRESSIVE EVIDENCE CHARTS
// ============================================================

/*
 * These charts are produced immediately from
 * every successful SQL result.
 *
 * IMPORTANT:
 *
 * No additional call to Qwen is made.
 *
 * SQL
 *   ↓
 * rows
 *   ↓
 * deterministic visualization decision
 *   ↓
 * Chart.js
 */


function buildProgressiveEvidenceChart(
    rows,
    title = "Evidence"
) {

    /*
     * A one-row result normally represents
     * a KPI/baseline.
     *
     * We keep that as text + table rather
     * than drawing a meaningless chart.
     */

    if (
        !Array.isArray(rows) ||
        rows.length < 2
    ) {
        return null;
    }


    const spec =
        inferProgressiveChartSpec(
            rows,
            title
        );


    if (!spec) {
        return null;
    }


    const wrap =
        document.createElement(
            "div"
        );

    wrap.className =
        "live-evidence-chart chart-canvas-wrap";

    /*
     * Explicit height is important because
     * Chart.js uses maintainAspectRatio:false.
     */

    wrap.style.height =
        "260px";

    wrap.style.marginTop =
        "14px";


    const canvas =
        document.createElement(
            "canvas"
        );

    wrap.appendChild(
        canvas
    );


    /*
     * Wait until the element has entered
     * the DOM/layout before Chart.js measures it.
     */

    requestAnimationFrame(
        () => {

            try {

                const chart =
                    new Chart(
                        canvas.getContext(
                            "2d"
                        ),

                        buildChartConfig(
                            spec,
                            rows
                        )
                    );

                activeCharts.add(
                    chart
                );

            } catch (error) {

                console.warn(
                    "Progressive chart could not be rendered:",
                    error
                );

                wrap.remove();
            }
        }
    );


    return wrap;
}


// ============================================================
// AUTOMATIC CHART SELECTION
// ============================================================

function inferProgressiveChartSpec(
    rows,
    title = "Evidence"
) {

    title = normalizeChartTitle(title, "Evidence");
    const fields =
        Object.keys(
            rows[0] || {}
        );


    if (!fields.length) {
        return null;
    }


    /*
     * Identify numeric columns.
     */

    const numericFields =
        fields.filter(
            field =>
                rows.some(
                    row =>
                        isFiniteNumber(
                            row[field]
                        )
                )
        );


    /*
     * Identify categorical/text columns.
     */

    const textFields =
        fields.filter(
            field =>
                rows.some(
                    row =>
                        row[field] !== null &&
                        row[field] !== undefined &&
                        row[field] !== "" &&
                        !isFiniteNumber(
                            row[field]
                        )
                )
        );


    /*
     * Date/time-like fields are useful
     * for line charts.
     */

    const dateField =
        fields.find(
            field =>
                looksLikeDateField(
                    field
                ) &&
                rows.some(
                    row =>
                        row[field] !== null &&
                        row[field] !== undefined
                )
        );


    /*
     * Prefer:
     *
     * date dimension
     * then first categorical dimension
     * then any non-numeric dimension.
     */

    const categoryField =
        dateField ||
        textFields[0] ||
        fields.find(
            field =>
                !numericFields.includes(
                    field
                )
        );


    /*
     * Select the most analytically useful
     * numeric metric.
     */

    const metricField =
        chooseProgressiveMetric(
            numericFields
        );


    /*
     * Categorical comparison.
     */

    if (
        categoryField &&
        metricField
    ) {

        return {
            type:
                dateField
                    ? "line"
                    : "bar",

            title,

            x:
                categoryField,

            y:
                metricField
        };
    }


    /*
     * If there is no categorical dimension,
     * but there are at least two numeric
     * variables and several observations,
     * a scatter plot is possible.
     */

    if (
        numericFields.length >= 2 &&
        rows.length >= 3
    ) {

        return {
            type: "scatter",

            title,

            x:
                numericFields[0],

            y:
                numericFields[1]
        };
    }


    return null;
}


// ============================================================
// METRIC SELECTION
// ============================================================

function chooseProgressiveMetric(
    numericFields
) {

    if (!numericFields.length) {
        return null;
    }


    /*
     * We prefer analytical rates over raw
     * counts when both are available.
     *
     * Example:
     *
     * business_unit
     * total_employees
     * left_employees
     * attrition_rate_percent
     *
     * → attrition_rate_percent
     */

    const priorities = [

        /attrition.*(rate|percent|percentage)/i,

        /(rate|percent|percentage).*attrition/i,

        /percentage/i,

        /percent/i,

        /rate/i,

        /ratio/i,

        /average|avg|mean/i,

        /median/i,

        /left|leaver|attrition/i,

        /count|total|employees/i
    ];


    for (
        const pattern
        of priorities
    ) {

        const match =
            numericFields.find(
                field =>
                    pattern.test(
                        field
                    )
            );


        if (match) {
            return match;
        }
    }


    /*
     * Last-resort deterministic choice.
     */

    return numericFields[
        numericFields.length - 1
    ];
}


// ============================================================
// TYPE HELPERS
// ============================================================

function looksLikeDateField(
    field
) {

    return /(^|_)(date|day|week|month|quarter|year|time)($|_)/i
        .test(
            String(
                field || ""
            )
        );
}


function isFiniteNumber(
    value
) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return false;
    }


    return Number.isFinite(
        Number(value)
    );
}

function normalizeChartTitle(value, fallback = "Visualization") {
    if (typeof value === "string" && value.trim()) {
        return value.trim();
    }

    if (value && typeof value === "object") {
        for (const key of ["label", "name", "title", "text"]) {
            if (typeof value[key] === "string" && value[key].trim()) {
                return value[key].trim();
            }
        }
    }

    return fallback;
}