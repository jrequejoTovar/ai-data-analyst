const API = {
    async analyze(question, onEvent) {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({question})
        });

        if (!response.ok) {
            let message = `Request failed with HTTP ${response.status}.`;
            try {
                const payload = await response.json();
                message = payload.detail || payload.error || message;
            } catch {}
            throw new Error(message);
        }

        if (!response.body) {
            throw new Error("Streaming is not supported by this browser.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalResult = null;

        while (true) {
            const {value, done} = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;
                const event = JSON.parse(line);

                if (event.type === "error") {
                    throw new Error(event.message || "Analysis failed.");
                }

                if (event.type === "result") {
                    finalResult = event.data;
                }

                onEvent?.(event);
            }
        }

        return finalResult;
    }
};
