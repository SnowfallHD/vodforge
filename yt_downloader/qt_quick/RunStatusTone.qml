import QtQuick

QtObject {
    function colorFor(kind, status, palette) {
        const value = String(status || "")
        if (value === "Failed") return palette.danger
        if (["Partial", "Stopped", "Skipped", "Cancelled", "Canceled"].includes(value))
            return palette.warning
        if (value === "Completed" || kind === "completed") return palette.success
        if (kind === "active" || kind === "queued" || kind === "preview")
            return palette.progress
        return palette.muted
    }

    function progressValue(kind, progress) {
        if (kind === "terminal" || kind === "completed") return 100
        const value = Number(progress || 0)
        return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0
    }

    function progressLabel(kind, status, progress) {
        if (kind === "terminal") return String(status || "Failed")
        if (kind === "queued") return "Queued"
        return Math.round(progressValue(kind, progress)) + "%"
    }
}
