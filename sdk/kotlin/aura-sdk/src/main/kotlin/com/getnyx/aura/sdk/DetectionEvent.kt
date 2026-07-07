// PROJECT AURA — public SDK detection types (Stage 9 §9).
// Idiomatic Kotlin mirror of core's common::DetectionEvent, with equivalent (not
// merely similar) semantics to IWakeWordListener::onWakeWordDetected (Stage 9 §9).
package com.getnyx.aura.sdk

/** The per-cascade correlation id (Stage 7 §12), threaded from VadTriggered. */
data class CorrelationId(val hi: Long, val lo: Long) {
    override fun toString(): String = hi.toULong().toString(16) + lo.toULong().toString(16)
}

/** Emitted when a configured wake word is detected. */
data class DetectionEvent(
    val correlationId: CorrelationId,
    /** Stage-1 confidence in [0, 1]. */
    val confidence: Float,
    /** Capture-clock monotonic nanoseconds at confirmation. */
    val timestampNanos: Long,
    /** Index of the configured wake word that matched. */
    val wakeWordIndex: Int,
)
