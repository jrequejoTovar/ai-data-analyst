const composer =
    document.getElementById("composer");

const questionInput =
    document.getElementById("question");

const sendButton =
    document.getElementById("sendButton");

const conversation =
    document.getElementById("conversation");

const welcome =
    document.getElementById("welcome");

const turnTemplate =
    document.getElementById("turnTemplate");


let isRunning = false;


/* =========================================================
   FORM
========================================================= */

composer.addEventListener("submit", async (event) => {

    event.preventDefault();

    const question =
        questionInput.value.trim();

    if (!question || isRunning) {
        return;
    }

    await runAnalysis(question);
});


questionInput.addEventListener("keydown", (event) => {

    if (
        event.key === "Enter" &&
        !event.shiftKey
    ) {
        event.preventDefault();

        composer.requestSubmit();
    }
});


questionInput.addEventListener("input", () => {

    questionInput.style.height = "auto";

    questionInput.style.height =
        `${Math.min(
            questionInput.scrollHeight,
            180
        )}px`;
});


document
    .querySelectorAll("[data-question]")
    .forEach(button => {

        button.addEventListener("click", async () => {

            if (isRunning) {
                return;
            }

            const question =
                button.dataset.question;

            questionInput.value =
                question;

            await runAnalysis(question);
        });
    });


/* =========================================================
   RUN ANALYSIS
========================================================= */

async function runAnalysis(question) {

    isRunning = true;

    sendButton.disabled = true;

    questionInput.disabled = true;


    if (welcome) {
        welcome.classList.add("hidden");
    }


    const turn =
        createTurn(question);


    questionInput.value = "";

    questionInput.style.height =
        "auto";


    scrollToTurn(turn);


    try {

        const result = await API.analyze(
            question,
            event => {
                handleEvent(
                    turn,
                    event
                );
            }
        );

        if (result) {
            renderFinal(
                turn,
                result
            );
        }

    } catch (error) {

        showError(
            turn,
            error
        );

    } finally {

        isRunning = false;

        sendButton.disabled = false;

        questionInput.disabled = false;

        questionInput.focus();
    }
}


/* =========================================================
   CREATE TURN
========================================================= */

function createTurn(question) {

    const fragment =
        turnTemplate.content.cloneNode(true);

    const turn =
        fragment.querySelector(".turn");

    const userBubble =
        turn.querySelector(".user-bubble");

    userBubble.textContent =
        question;


    conversation.appendChild(fragment);


    return conversation.lastElementChild;
}


/* =========================================================
   STREAM EVENTS
========================================================= */

function handleEvent(turn, event) {

    if (!event) {
        return;
    }


    /*
     * Final result
     */

    if (event.type === "result") {

        renderFinal(
            turn,
            event.result
        );

        return;
    }


    /*
     * Router / strategy
     */

    if (event.type === "strategy") {

        updateActivityHeader(
            turn,
            event.message ||
            "Analytical strategy selected."
        );

        appendActivity(
            turn,
            event.message ||
            "Analytical strategy selected.",
            event.duration_seconds
        );

        return;
    }


    /*
     * Analytical phase
     */

    if (event.type === "phase") {

        updateActivityHeader(
            turn,
            event.message ||
            "Continuing analysis."
        );

        appendActivity(
            turn,
            event.message ||
            "Continuing analysis.",
            event.duration_seconds
        );

        return;
    }


    /*
     * Model decision / reasoning step
     */

    if (event.type === "model") {

        const message =
            event.message ||
            "Model completed analytical step.";

        updateActivityHeader(
            turn,
            message
        );

        appendActivity(
            turn,
            message,
            event.duration_seconds
        );

        return;
    }


    /*
     * Tool execution
     */

    if (event.type === "tool") {

        appendToolActivity(
            turn,
            event
        );


        /*
         * Every successful SQL result becomes
         * provisional evidence immediately.
         */

        if (
            event.status === "complete" &&
            event.tool === "execute_sql" &&
            event.result
        ) {

            appendLiveEvidence(
                turn,
                event
            );
        }

        return;
    }


    /*
     * Generic progress
     */

    if (event.message) {

        updateActivityHeader(
            turn,
            event.message
        );

        appendActivity(
            turn,
            event.message,
            event.duration_seconds
        );
    }
}


/* =========================================================
   ACTIVITY HEADER
========================================================= */

function updateActivityHeader(turn, message) {

    const title =
        turn.querySelector(".activity-title");

    const activityMessage =
        turn.querySelector(".activity-message");


    if (title) {

        title.textContent =
            "Analysis in progress";
    }


    if (activityMessage) {

        activityMessage.textContent =
            message;
    }
}


/* =========================================================
   ACTIVITY
========================================================= */

function appendActivity(
    turn,
    message,
    durationSeconds
) {

    const detail =
        turn.querySelector(".activity-detail");

    if (!detail) {
        return;
    }


    const row =
        document.createElement("div");

    row.className =
        "activity-line";


    const text =
        document.createElement("span");

    text.textContent =
        message;


    row.appendChild(text);


    if (
        durationSeconds !== undefined &&
        durationSeconds !== null
    ) {

        const duration =
            document.createElement("span");

        duration.className =
            "activity-duration";

        duration.textContent =
            formatDuration(
                durationSeconds
            );

        row.appendChild(duration);
    }


    detail.appendChild(row);


    scrollToTurn(turn);
}


/* =========================================================
   TOOL ACTIVITY
========================================================= */

function appendToolActivity(turn, event) {

    const detail =
        turn.querySelector(".activity-detail");

    if (!detail) {
        return;
    }


    const row =
        document.createElement("div");

    row.className =
        "activity-line tool-activity";


    const status =
        event.status || "running";

    const tool =
        event.tool || "tool";


    let prefix = "→";

    if (status === "complete") {
        prefix = "✓";
    }

    if (status === "error") {
        prefix = "×";
    }


    const text =
        document.createElement("span");

    text.textContent =
        `${prefix} ${friendlyToolName(tool)}`;


    row.appendChild(text);


    if (
        event.duration_seconds !== undefined &&
        event.duration_seconds !== null
    ) {

        const duration =
            document.createElement("span");

        duration.className =
            "activity-duration";

        duration.textContent =
            formatDuration(
                event.duration_seconds
            );

        row.appendChild(duration);
    }


    detail.appendChild(row);


    if (status === "running") {

        updateActivityHeader(
            turn,
            friendlyToolMessage(tool)
        );
    }


    scrollToTurn(turn);
}


/* =========================================================
   PROGRESSIVE EVIDENCE
========================================================= */

function appendLiveEvidence(turn, event) {

    const section =
        turn.querySelector(".live-evidence");

    const list =
        turn.querySelector(".live-evidence-list");

    const count =
        turn.querySelector(".live-evidence-count");


    if (!section || !list) {
        return;
    }


    let rows = [];


    try {

        rows =
            parseEvidenceRows(
                event.result
            );

    } catch (error) {

        console.warn(
            "Could not parse progressive evidence:",
            error
        );

        return;
    }


    if (
        !Array.isArray(rows) ||
        rows.length === 0
    ) {
        return;
    }


    section.classList.remove("hidden");


    const item =
        document.createElement("article");

    item.className =
        "live-evidence-item";


    const summary =
        buildEvidenceSummary(
            rows,
            event
        );


    const head =
        document.createElement("div");

    head.className =
        "live-evidence-item-head";


    const check =
        document.createElement("span");

    check.className =
        "live-evidence-check";

    check.textContent =
        "✓";


    const copy =
        document.createElement("div");


    const title =
        document.createElement("strong");

    title.textContent =
        summary.title;


    const description =
        document.createElement("p");

    description.textContent =
        summary.description;


    copy.appendChild(title);

    copy.appendChild(description);


    head.appendChild(check);

    head.appendChild(copy);


    item.appendChild(head);


    /*
     * Add the item to the DOM BEFORE creating
     * the Chart.js canvas. This gives Chart.js
     * a real layout size.
     */

    list.appendChild(item);


    /*
     * Progressive chart
     */

    if (
        typeof buildProgressiveEvidenceChart ===
        "function"
    ) {

        try {

            const chartTitle =
                normalizeChartTitle(
                    summary.title,
                    "Evidence"
                );

            const chart =
                buildProgressiveEvidenceChart(
                    rows,
                    chartTitle
                );

            if (chart) {
                item.appendChild(chart);
            }

        } catch (error) {

            console.warn(
                "Progressive chart could not be created:",
                error
            );
        }
    }


    /*
     * Progressive table
     */

    const preview =
        buildEvidencePreview(rows);


    if (preview) {

        item.appendChild(preview);
    }


    /*
     * Update evidence count
     */

    if (count) {

        const total =
            list.children.length;

        count.textContent =
            `${total} evidence item${
                total === 1 ? "" : "s"
            }`;
    }


    scrollToTurn(turn);
}


/* =========================================================
   EVIDENCE SUMMARY
========================================================= */

function buildEvidenceSummary(rows, event) {

    const columns =
        Object.keys(
            rows[0] || {}
        );


    if (rows.length === 1) {

        const numericColumn =
            columns.find(column =>
                isNumericValue(
                    rows[0][column]
                )
            );


        if (numericColumn) {

            return {
                title:
                    humanizeLabel(
                        numericColumn
                    ),

                description:
                    `Evidence returned from ${friendlyToolName(
                        event.tool
                    )}.`
            };
        }
    }


    const metric =
        chooseSummaryMetric(
            rows
        );


    const dimension =
        columns.find(
            column =>
                column !== metric
        );
    console.log("PROGRESSIVE TITLE DEBUG:", {
        dimension,
        metric,
        metricType: typeof metric,
        dimensionType: typeof dimension
    });

    if (dimension && metric) {

    const metricName =
        typeof metric === "string"
            ? metric
            : Object.keys(metric).find(
                key =>
                    key !== dimension &&
                    rows.some(
                        row =>
                            row[key] !== null &&
                            row[key] !== undefined &&
                            row[key] !== "" &&
                            Number.isFinite(Number(row[key]))
                    )
            );

    return {
        title:
            `${humanizeLabel(metricName || "Value")} by ${humanizeLabel(dimension)}`,

        description:
            `${rows.length} groups compared.`
    };
}


    return {
        title:
            "Evidence collected",

        description:
            `${rows.length} rows returned.`
    };
}


/* =========================================================
   CHOOSE SUMMARY METRIC
========================================================= */

function chooseSummaryMetric(rows) {

    if (
        typeof chooseProgressiveMetric ===
        "function"
    ) {

        try {

            const metric =
                chooseProgressiveMetric(
                    rows
                );

            if (metric) {
                return metric;
            }

        } catch (error) {

            console.warn(
                "Progressive metric selection failed:",
                error
            );
        }
    }


    const first =
        rows[0] || {};


    const columns =
        Object.keys(first);


    return columns.find(column =>
        isNumericValue(
            first[column]
        )
    );
}


/* =========================================================
   EVIDENCE TABLE
========================================================= */

function buildEvidencePreview(rows) {

    if (
        !Array.isArray(rows) ||
        rows.length === 0
    ) {
        return null;
    }


    const wrapper =
        document.createElement("div");

    wrapper.className =
        "live-evidence-preview";


    const table =
        document.createElement("table");


    const columns =
        Object.keys(
            rows[0]
        );


    const thead =
        document.createElement("thead");

    const headRow =
        document.createElement("tr");


    columns.forEach(column => {

        const th =
            document.createElement("th");

        th.textContent =
            humanizeLabel(column);

        headRow.appendChild(th);
    });


    thead.appendChild(headRow);

    table.appendChild(thead);


    const tbody =
        document.createElement("tbody");


    /*
     * Keep progressive tables compact.
     */

    rows
        .slice(0, 12)
        .forEach(row => {

            const tr =
                document.createElement("tr");


            columns.forEach(column => {

                const td =
                    document.createElement("td");

                td.textContent =
                    formatCellValue(
                        row[column],
                        column
                    );

                tr.appendChild(td);
            });


            tbody.appendChild(tr);
        });


    table.appendChild(tbody);

    wrapper.appendChild(table);


    if (rows.length > 12) {

        const note =
            document.createElement("div");

        note.className =
            "table-note";

        note.textContent =
            `Showing 12 of ${rows.length} rows.`;

        wrapper.appendChild(note);
    }


    return wrapper;
}


/* =========================================================
   FINAL RESULT
========================================================= */

function renderFinal(turn, result) {

    const finalAnswer =
        turn.querySelector(".final-answer");

    const answerText =
        turn.querySelector(".answer-text");

    const insights =
        turn.querySelector(".insights");

    const evidenceList =
        turn.querySelector(".evidence-list");

    const traceList =
        turn.querySelector(".trace-list");

    const visualEvidence =
        turn.querySelector(".visual-evidence");

    const chartsGrid =
        turn.querySelector(".charts-grid");

    const timingElement =
        turn.querySelector(".analysis-timing");


    const analysis =
        result?.analysis || {};

    const evidence =
        Array.isArray(result?.evidence)
            ? result.evidence
            : [];

    const trace =
        Array.isArray(result?.trace)
            ? result.trace
            : [];

    const timing =
        result?.timing || {};


    /*
     * Answer
     */

    renderMarkdown(
        answerText,
        analysis.answer ||
        "Analysis completed."
    );


    /*
     * Total analysis time
     */

    if (
        timingElement &&
        timing.total_seconds !== undefined
    ) {

        timingElement.textContent =
            `Total analysis time: ${formatDuration(
                timing.total_seconds
            )}`;
    }


    /*
     * Investigation-only insight sections
     */

    if (insights) {

        insights.innerHTML = "";


        if (
            result?.mode === "INVESTIGATE"
        ) {

            renderInsightSection(
                insights,
                "Facts",
                analysis.facts
            );

            renderInsightSection(
                insights,
                "Observations",
                analysis.observations
            );

            renderInsightSection(
                insights,
                "Hypotheses",
                analysis.hypotheses
            );

            renderInsightSection(
                insights,
                "Recommendations",
                analysis.recommendations
            );
        }
    }


    /*
     * Final charts
     */

    if (
        chartsGrid &&
        typeof renderVisualizationsInto ===
        "function"
    ) {

        const visualizations =
            Array.isArray(
                analysis.visualizations
            )
                ? analysis.visualizations
                : [];


        if (visualizations.length) {

            visualEvidence.classList.remove(
                "hidden"
            );


            renderVisualizationsInto(
                chartsGrid,
                visualizations,
                evidence
            );

        } else {

            visualEvidence.classList.add(
                "hidden"
            );
        }
    }


    /*
     * Evidence ledger
     */

    renderEvidenceLedger(
        evidenceList,
        evidence
    );


    /*
     * Agent trace
     */

    renderTrace(
        traceList,
        trace
    );


    /*
     * Mark inner activity complete.
     */

    const activityCard =
        turn.querySelector(".activity-card");

    const activityTitle =
        turn.querySelector(".activity-title");

    const activityMessage =
        turn.querySelector(".activity-message");

    const pulse =
        turn.querySelector(".activity-pulse");


    if (activityTitle) {

        activityTitle.textContent =
            "Analysis completed";
    }


    if (activityMessage) {

        activityMessage.textContent =
            "The agent has completed the investigation and synthesized the available evidence.";
    }


    if (pulse) {

        pulse.classList.add(
            "complete"
        );
    }


    if (activityCard) {

        activityCard.open = false;
    }


    /*
     * Mark progressive evidence complete.
     */

    /*
    * Mark progressive evidence complete.
    */

    const liveEvidence =
        turn.querySelector(".live-evidence");

    if (liveEvidence) {

        liveEvidence.classList.add("complete");

        const evidenceKicker =
            liveEvidence.querySelector(
                ".live-evidence-kicker"
            );

        const evidenceStatus =
            liveEvidence.querySelector(
                ".live-evidence-status"
            );

        const evidenceCount =
            liveEvidence.querySelector(
                ".live-evidence-count"
            );

        if (evidenceKicker) {
            evidenceKicker.textContent =
                "Evidence collected";
        }

        if (evidenceStatus) {
            evidenceStatus.textContent =
                "Analysis completed";
        }

        if (evidenceCount) {
            evidenceCount.textContent =
                `${evidence.length} evidence item${
                    evidence.length === 1 ? "" : "s"
                }`;
        }
    }

    


    /*
     * OUTER INVESTIGATION WORKSPACE
     *
     * During analysis it remains open so the
     * user can watch evidence accumulate.
     *
     * When synthesis is complete it collapses
     * automatically, giving visual priority to
     * the final answer.
     */

    const investigationCard =
        turn.querySelector(
            ".investigation-card"
        );

    const investigationTitle =
        turn.querySelector(
            ".investigation-title"
        );

    const investigationMeta =
        turn.querySelector(
            ".investigation-meta"
        );

    const investigationPulse =
        turn.querySelector(
            ".investigation-pulse"
        );


    if (investigationCard) {

        investigationCard.classList.add(
            "complete"
        );

        investigationCard.open =
            false;
    }


    if (investigationTitle) {

        investigationTitle.textContent =
            "Investigation completed";
    }


    if (investigationPulse) {

        investigationPulse.classList.add(
            "complete"
        );
    }


    if (investigationMeta) {

        const metaParts = [];


        if (evidence.length) {

            metaParts.push(
                `${evidence.length} evidence item${
                    evidence.length === 1
                        ? ""
                        : "s"
                }`
            );
        }


        if (
            timing.total_seconds !== undefined
        ) {

            metaParts.push(
                formatDuration(
                    timing.total_seconds
                )
            );
        }


        investigationMeta.textContent =
            metaParts.length
                ? metaParts.join(" · ")
                : "Analysis completed";
    }


    /*
     * Show final answer AFTER the investigation
     * workspace has been collapsed.
     */

    finalAnswer.classList.remove(
        "hidden"
    );


    scrollToFinalAnswer(
        turn
    );
}


/* =========================================================
   INSIGHT SECTIONS
========================================================= */

function renderInsightSection(
    container,
    title,
    items
) {

    if (
        !Array.isArray(items) ||
        items.length === 0
    ) {
        return;
    }


    const section =
        document.createElement("section");

    section.className =
        "insight-section";


    const heading =
        document.createElement("h3");

    heading.textContent =
        title;


    section.appendChild(heading);


    const list =
        document.createElement("ul");


    items.forEach(item => {

        const li =
            document.createElement("li");


        if (
            typeof item === "string"
        ) {

            li.textContent =
                item;

        } else {

            const text =
                item.text ||
                item.statement ||
                item.finding ||
                item.description ||
                JSON.stringify(item);

            renderMarkdown(
                li,
                text
            );
        }


        list.appendChild(li);
    });


    section.appendChild(list);

    container.appendChild(section);
}


/* =========================================================
   EVIDENCE LEDGER
========================================================= */

function renderEvidenceLedger(
    container,
    evidence
) {

    if (!container) {
        return;
    }


    container.innerHTML = "";


    if (
        !Array.isArray(evidence) ||
        evidence.length === 0
    ) {

        container.textContent =
            "No evidence ledger was returned.";

        return;
    }


    evidence.forEach(item => {

        const card =
            document.createElement("div");

        card.className =
            "evidence-item";


        const title =
            document.createElement("strong");

        title.textContent =
            item.id ||
            item.label ||
            "Evidence";


        card.appendChild(title);


        const source =
            document.createElement("div");

        source.className =
            "evidence-source";

        source.textContent =
            item.source ||
            item.tool ||
            "Internal data";


        card.appendChild(source);


        if (item.query) {

            const query =
                document.createElement("pre");

            query.textContent =
                item.query;

            card.appendChild(query);
        }


        if (item.result) {

            const result =
                document.createElement("pre");

            result.textContent =
                typeof item.result === "string"
                    ? item.result
                    : JSON.stringify(
                        item.result,
                        null,
                        2
                    );

            card.appendChild(result);
        }


        container.appendChild(card);
    });
}


/* =========================================================
   TRACE
========================================================= */

function renderTrace(
    container,
    trace
) {

    if (!container) {
        return;
    }


    container.innerHTML = "";


    if (
        !Array.isArray(trace) ||
        trace.length === 0
    ) {

        container.textContent =
            "No operational trace was returned.";

        return;
    }


    trace.forEach(item => {

        const row =
            document.createElement("div");

        row.className =
            "trace-item";


        if (
            typeof item === "string"
        ) {

            row.textContent =
                item;

        } else {

            const action =
                item.action ||
                item.tool ||
                item.type ||
                "Step";

            const status =
                item.status
                    ? ` · ${item.status}`
                    : "";

            row.textContent =
                `${action}${status}`;


            if (
                item.duration_seconds !== undefined
            ) {

                const duration =
                    document.createElement("span");

                duration.className =
                    "activity-duration";

                duration.textContent =
                    formatDuration(
                        item.duration_seconds
                    );

                row.appendChild(duration);
            }
        }


        container.appendChild(row);
    });
}


/* =========================================================
   MARKDOWN
========================================================= */

function renderMarkdown(
    element,
    markdown
) {

    if (!element) {
        return;
    }


    const text =
        String(
            markdown || ""
        );


    if (
        typeof marked !== "undefined" &&
        typeof DOMPurify !== "undefined"
    ) {

        const html =
            marked.parse(text);

        element.innerHTML =
            DOMPurify.sanitize(html);

        return;
    }


    element.textContent =
        text;
}


/* =========================================================
   FORMAT HELPERS
========================================================= */

function friendlyToolName(tool) {

    const names = {

        list_schemas:
            "Inspect database schemas",

        list_objects:
            "Inspect available data objects",

        get_object_details:
            "Inspect dataset metadata",

        execute_sql:
            "Query the data"
    };


    return names[tool] || tool;
}


function friendlyToolMessage(tool) {

    const messages = {

        list_schemas:
            "Discovering available database schemas.",

        list_objects:
            "Discovering available datasets.",

        get_object_details:
            "Understanding fields and semantic metadata.",

        execute_sql:
            "Testing the data and collecting evidence."
    };


    return messages[tool] ||
        "Using an analytical tool.";
}


function formatDuration(seconds) {

    const value =
        Number(seconds);


    if (!Number.isFinite(value)) {

        return "";
    }


    if (value < 1) {

        return `${Math.round(
            value * 1000
        )} ms`;
    }


    return `${value.toFixed(1)} s`;
}


function humanizeLabel(value) {

    return String(value ?? "")
        // Separate camelCase and PascalCase
        .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
        // Handle acronyms such as XMLParser
        .replace(/([A-Z])([A-Z][a-z])/g, "$1 $2")
        // Replace underscores with spaces
        .replace(/_/g, " ")
        // Normalize whitespace
        .replace(/\s+/g, " ")
        .trim()
        // Capitalize each word
        .replace(/\b\w/g, char =>
            char.toUpperCase()
        );
}


function isNumericValue(value) {

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


function formatCellValue(
    value,
    column
) {

    if (
        value === null ||
        value === undefined
    ) {
        return "—";
    }


    const numeric =
        Number(value);


    if (
        Number.isFinite(numeric)
    ) {

        const name =
            String(column || "")
                .toLowerCase();


        if (
            name.includes("percent") ||
            name.includes("percentage") ||
            name.includes("rate") ||
            name.includes("ratio")
        ) {

            return numeric.toLocaleString(
                undefined,
                {
                    maximumFractionDigits: 2
                }
            );
        }


        return numeric.toLocaleString(
            undefined,
            {
                maximumFractionDigits: 2
            }
        );
    }


    return String(value);
}


/* =========================================================
   SCROLL
========================================================= */

function scrollToTurn(turn) {

    requestAnimationFrame(() => {

        const rect =
            turn.getBoundingClientRect();


        if (
            rect.bottom >
            window.innerHeight - 140
        ) {

            window.scrollTo({
                top:
                    window.scrollY +
                    rect.bottom -
                    window.innerHeight +
                    170,

                behavior:
                    "smooth"
            });
        }
    });
}


function scrollToFinalAnswer(turn) {

    requestAnimationFrame(() => {

        const finalAnswer =
            turn.querySelector(
                ".final-answer"
            );


        if (!finalAnswer) {
            return;
        }


        const top =
            finalAnswer.getBoundingClientRect().top +
            window.scrollY -
            90;


        window.scrollTo({
            top,
            behavior: "smooth"
        });
    });
}


/* =========================================================
   ERROR
========================================================= */

function showError(turn, error) {

    console.error(error);


    const activityTitle =
        turn.querySelector(
            ".activity-title"
        );

    const activityMessage =
        turn.querySelector(
            ".activity-message"
        );

    const investigationTitle =
        turn.querySelector(
            ".investigation-title"
        );

    const investigationMeta =
        turn.querySelector(
            ".investigation-meta"
        );


    if (activityTitle) {

        activityTitle.textContent =
            "Analysis failed";
    }


    if (activityMessage) {

        activityMessage.textContent =
            error?.message ||
            "An unexpected error occurred.";
    }


    if (investigationTitle) {

        investigationTitle.textContent =
            "Investigation interrupted";
    }


    if (investigationMeta) {

        investigationMeta.textContent =
            error?.message ||
            "The analysis could not be completed.";
    }
}